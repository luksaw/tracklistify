"""Parser for MixesDB wikitext tracklists."""

import re
from dataclasses import dataclass

from mixesdbsync.mixesdb.models import Mix, MixTrack


@dataclass
class ParseResult:
    """Result of parsing a MixesDB page."""

    mix: Mix
    raw_wikitext: str


class TracklistParser:
    """Parse MixesDB wikitext tracklists."""

    # Pattern: # Artist - Track Title [Label]
    # Also handles: # [MM] Artist - Track Title [Label] (with optional timestamp)
    TRACK_PATTERN = re.compile(
        r"^\#\s*"  # Numbered list marker
        r"(?:\[(\d+)\])?\s*"  # Optional timestamp [MM]
        r"(.+?)\s+-\s+"  # Artist name (non-greedy, followed by " - ")
        r"(.+?)"  # Track title (non-greedy)
        r"(?:\s*\[([^\]]+)\])?\s*$"  # Optional label [Label]
    )

    # Common remix indicators to extract from title
    REMIX_PATTERN = re.compile(
        r"\(([^)]*(?:Remix|Mix|Edit|Version|Dub|Rework|Bootleg)[^)]*)\)",
        re.IGNORECASE,
    )

    # Pattern to extract page title components
    TITLE_PATTERN = re.compile(
        r"^(\d{4}-\d{2}-\d{2})_-_(.+?)_-_(.+)$"  # Date_-_Artist_-_Title
    )

    def parse(self, wikitext: str, url: str) -> ParseResult:
        """Parse wikitext and extract tracklist."""
        # Extract page title from URL
        page_title = self._extract_page_title(url)
        mix_title = self._format_mix_title(page_title)

        # Parse tracks
        tracks = self._parse_tracks(wikitext)

        # Extract additional metadata
        categories = self._extract_categories(wikitext)
        spotify_url = self._extract_player_url(wikitext, "spotify")
        soundcloud_url = self._extract_player_url(wikitext, "soundcloud")

        # Extract image filename (URL will be resolved by client)
        image_filename = self._extract_image_filename(wikitext)

        mix = Mix(
            url=url,
            title=mix_title,
            tracks=tracks,
            categories=categories,
            spotify_url=spotify_url,
            soundcloud_url=soundcloud_url,
            image_url=None,  # Will be resolved by client
        )
        # Store filename for later resolution
        mix._image_filename = image_filename  # type: ignore

        return ParseResult(mix=mix, raw_wikitext=wikitext)

    def _parse_tracks(self, wikitext: str) -> list[MixTrack]:
        """Extract tracks from wikitext."""
        tracks: list[MixTrack] = []
        position = 0

        for line in wikitext.split("\n"):
            line = line.strip()
            if not line.startswith("#"):
                continue

            # Skip lines that look like comments or section markers
            if line.startswith("##") or "==" in line:
                continue

            # Clean wiki links before parsing
            cleaned_line = self._clean_wiki_links(line)

            match = self.TRACK_PATTERN.match(cleaned_line)
            if match:
                position += 1
                _timestamp, artist, title, label = match.groups()

                # Extract remix info from title
                remix = None
                remix_match = self.REMIX_PATTERN.search(title)
                if remix_match:
                    remix = remix_match.group(1)

                tracks.append(
                    MixTrack(
                        position=position,
                        artist=artist.strip(),
                        title=title.strip(),
                        label=label.strip() if label else None,
                        remix=remix,
                    )
                )

        return tracks

    def _clean_wiki_links(self, text: str) -> str:
        """Convert [[Link|Display]] to Display, [[Link]] to Link."""
        # [[Artist|Display Name]] -> Display Name
        text = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)
        # [[Artist]] -> Artist
        text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
        return text

    def _extract_page_title(self, url: str) -> str:
        """Extract page title from MixesDB URL."""
        # Handle both /w/ and /db/ paths
        patterns = [
            r"mixesdb\.com/w/(.+?)(?:\?|#|$)",
            r"mixesdb\.com/db/(.+?)(?:\?|#|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                from urllib.parse import unquote

                return unquote(match.group(1))
        # Fallback: use the last path segment
        return url.rstrip("/").split("/")[-1]

    def _format_mix_title(self, page_title: str) -> str:
        """Convert page title to readable format."""
        # Replace underscores with spaces
        title = page_title.replace("_", " ")
        # Try to parse date-artist-event pattern
        match = self.TITLE_PATTERN.match(page_title)
        if match:
            date, artist, event = match.groups()
            artist = artist.replace("_", " ")
            event = event.replace("_", " ")
            return f"{artist} - {event} ({date})"
        return title

    def _extract_categories(self, wikitext: str) -> list[str]:
        """Extract category tags from wikitext."""
        categories = []
        pattern = r"\[\[Category:([^\]]+)\]\]"
        for match in re.finditer(pattern, wikitext):
            categories.append(match.group(1))
        return categories

    def _extract_player_url(self, wikitext: str, platform: str) -> str | None:
        """Extract player URL for a specific platform."""
        patterns = {
            "spotify": r"(https?://open\.spotify\.com/[^\s\]|]+)",
            "soundcloud": r"(https?://soundcloud\.com/[^\s\]|]+)",
            "youtube": r"(https?://(?:www\.)?youtu(?:be\.com|\.be)/[^\s\]|]+)",
            "mixcloud": r"(https?://(?:www\.)?mixcloud\.com/[^\s\]|]+)",
        }
        pattern = patterns.get(platform)
        if pattern:
            match = re.search(pattern, wikitext)
            if match:
                return match.group(1)
        return None

    def _extract_image_filename(self, wikitext: str) -> str | None:
        """Extract first image filename from wikitext."""
        # Pattern: [[File:filename.jpg|...]] or [[Image:filename.jpg|...]]
        pattern = r"\[\[(?:File|Image):([^\]|]+)"
        match = re.search(pattern, wikitext, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
