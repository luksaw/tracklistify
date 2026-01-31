"""Spotify API client wrapper."""

from pathlib import Path
from typing import Any

import httpx
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from mixesdbsync.config import SpotifyConfig
from mixesdbsync.spotify.models import SpotifyPlaylist, SpotifyTrack

# Required OAuth scopes
SPOTIFY_SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "ugc-image-upload",  # Required for playlist cover images
]


class SpotifyError(Exception):
    """Base exception for Spotify errors."""

    pass


class SpotifyAuthError(SpotifyError):
    """Authentication failed."""

    pass


class SpotifyRateLimitError(SpotifyError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int = 5):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


class SpotifyClient:
    """High-level Spotify API client."""

    def __init__(self, config: SpotifyConfig, cache_path: Path | None = None):
        self.config = config
        self._sp: spotipy.Spotify | None = None
        self._cache_path = cache_path or Path.home() / ".mixesdbsync" / ".spotify_cache"

    @property
    def sp(self) -> spotipy.Spotify:
        """Get or create authenticated Spotify client."""
        if self._sp is None:
            self._sp = self._create_client()
        return self._sp

    def _create_client(self) -> spotipy.Spotify:
        """Create authenticated Spotify client."""
        if not self.config.is_configured:
            raise SpotifyAuthError(
                "Spotify credentials not configured. "
                "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables "
                "or create a .env file."
            )

        # Ensure cache directory exists
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)

        auth_manager = SpotifyOAuth(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret.get_secret_value(),
            redirect_uri=self.config.redirect_uri,
            scope=" ".join(SPOTIFY_SCOPES),
            cache_path=str(self._cache_path),
            open_browser=True,
        )

        return spotipy.Spotify(auth_manager=auth_manager)

    def authenticate(self) -> bool:
        """Force authentication flow."""
        try:
            # This will trigger OAuth flow if needed
            user = self.sp.current_user()
            return user is not None
        except Exception as e:
            raise SpotifyAuthError(f"Authentication failed: {e}")

    def get_current_user(self) -> dict[str, Any]:
        """Get current user info."""
        return self.sp.current_user()

    @retry(
        retry=retry_if_exception_type(SpotifyRateLimitError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
    )
    def search_track(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SpotifyTrack]:
        """Search for tracks on Spotify."""
        try:
            results = self.sp.search(q=query, type="track", limit=limit)
            tracks = results.get("tracks", {}).get("items", [])
            return [SpotifyTrack.from_api_response(t) for t in tracks]
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                retry_after = int(e.headers.get("Retry-After", 5)) if e.headers else 5
                raise SpotifyRateLimitError(retry_after)
            raise SpotifyError(f"Search failed: {e}")

    def search_track_exact(self, artist: str, title: str, limit: int = 5) -> list[SpotifyTrack]:
        """Search with exact artist and track fields."""
        query = f'artist:"{artist}" track:"{title}"'
        return self.search_track(query, limit)

    def search_track_general(self, artist: str, title: str, limit: int = 10) -> list[SpotifyTrack]:
        """Search with general query."""
        query = f"{artist} {title}"
        return self.search_track(query, limit)

    def create_playlist(
        self,
        name: str,
        description: str = "",
        public: bool = True,
    ) -> SpotifyPlaylist:
        """Create a new playlist."""
        user_id = self.sp.current_user()["id"]
        result = self.sp.user_playlist_create(
            user=user_id,
            name=name,
            public=public,
            description=description,
        )
        return SpotifyPlaylist.from_api_response(result)

    def add_tracks_to_playlist(
        self,
        playlist_id: str,
        track_uris: list[str],
    ) -> None:
        """Add tracks to a playlist (handles batching)."""
        # Spotify API allows max 100 tracks per request
        batch_size = 100
        for i in range(0, len(track_uris), batch_size):
            batch = track_uris[i : i + batch_size]
            self.sp.playlist_add_items(playlist_id, batch)

    def find_existing_playlist(self, name: str) -> SpotifyPlaylist | None:
        """Find an existing playlist by name."""
        offset = 0
        limit = 50

        while True:
            results = self.sp.current_user_playlists(limit=limit, offset=offset)
            playlists = results.get("items", [])

            if not playlists:
                break

            for playlist in playlists:
                if playlist["name"] == name:
                    return SpotifyPlaylist.from_api_response(playlist)

            offset += limit

        return None

    def clear_playlist(self, playlist_id: str) -> None:
        """Remove all tracks from a playlist."""
        self.sp.playlist_replace_items(playlist_id, [])

    def set_playlist_cover_image(self, playlist_id: str, image_url: str) -> bool:
        """
        Download image from URL and set as playlist cover.
        Returns True if successful, False otherwise.
        """
        import base64
        from io import BytesIO

        try:
            # Download image
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                response = client.get(image_url)
                response.raise_for_status()
                image_data = response.content

            # Check if we need to process the image (resize/convert)
            # Spotify accepts JPEG, max 256KB
            if len(image_data) > 256 * 1024:
                # Try to compress/resize using PIL if available
                try:
                    from PIL import Image

                    img = Image.open(BytesIO(image_data))
                    # Convert to RGB if necessary (for PNG with transparency)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")

                    # Resize if too large (max 640x640 for Spotify)
                    max_size = 640
                    if img.width > max_size or img.height > max_size:
                        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                    # Save as JPEG with compression
                    buffer = BytesIO()
                    quality = 85
                    while quality > 20:
                        buffer.seek(0)
                        buffer.truncate()
                        img.save(buffer, format="JPEG", quality=quality)
                        if buffer.tell() <= 256 * 1024:
                            break
                        quality -= 10

                    image_data = buffer.getvalue()
                except ImportError:
                    # PIL not available, try to use image as-is
                    pass

            # Encode as base64
            image_b64 = base64.b64encode(image_data).decode("utf-8")

            # Upload to Spotify
            self.sp.playlist_upload_cover_image(playlist_id, image_b64)
            return True

        except Exception as e:
            # Image upload is optional, don't fail the whole sync
            import logging
            logging.getLogger("mixesdbsync").warning(f"Failed to set playlist cover: {e}")
            return False
