"""MixesDB MediaWiki API client."""

import re
from urllib.parse import unquote

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from mixesdbsync.mixesdb.models import Mix
from mixesdbsync.mixesdb.parser import TracklistParser


class MixesDBError(Exception):
    """Base exception for MixesDB errors."""

    pass


class MixNotFoundError(MixesDBError):
    """Requested mix page does not exist."""

    pass


class MixesDBClient:
    """Client for MixesDB MediaWiki API."""

    BASE_URL = "https://www.mixesdb.com/db/api.php"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.parser = TracklistParser()

    @staticmethod
    def extract_page_title(url: str) -> str:
        """
        Extract page title from MixesDB URL.

        Examples:
            https://www.mixesdb.com/w/2019-05-12_-_Lukas_Sawicki_-_Huone_005
            -> "2019-05-12_-_Lukas_Sawicki_-_Huone_005"
        """
        pattern = r"mixesdb\.com/w/(.+?)(?:\?|#|$)"
        match = re.search(pattern, url)
        if match:
            return unquote(match.group(1))
        raise ValueError(f"Invalid MixesDB URL: {url}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
    )
    def get_wikitext(self, page_title: str) -> str:
        """Fetch raw wikitext for a page."""
        params = {
            "action": "parse",
            "page": page_title,
            "prop": "wikitext",
            "format": "json",
        }

        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                error_info = data["error"].get("info", "Unknown error")
                if "missingtitle" in data["error"].get("code", ""):
                    raise MixNotFoundError(f"Mix not found: {page_title}")
                raise MixesDBError(f"API error: {error_info}")

            try:
                return data["parse"]["wikitext"]["*"]
            except KeyError as e:
                raise MixesDBError(f"Unexpected API response format: {e}")

    def fetch_mix(self, url: str) -> Mix:
        """Fetch and parse a mix from its URL."""
        page_title = self.extract_page_title(url)
        wikitext = self.get_wikitext(page_title)
        result = self.parser.parse(wikitext, url)
        mix = result.mix

        # Resolve image URL if filename was found
        image_filename = getattr(mix, "_image_filename", None)
        if image_filename:
            mix.image_url = self.get_image_url(image_filename)

        return mix

    def get_image_url(self, filename: str) -> str | None:
        """Get full URL for a MixesDB image file."""
        params = {
            "action": "query",
            "titles": f"File:{filename}",
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        }

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                pages = data.get("query", {}).get("pages", {})
                for page_data in pages.values():
                    imageinfo = page_data.get("imageinfo", [])
                    if imageinfo:
                        return imageinfo[0].get("url")
        except Exception:
            pass  # Image is optional, don't fail if we can't get it

        return None

    def fetch_mix_sync(self, url: str) -> Mix:
        """Synchronous version of fetch_mix (alias for fetch_mix)."""
        return self.fetch_mix(url)
