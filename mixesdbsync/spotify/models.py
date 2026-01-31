"""Data models for Spotify entities."""

from dataclasses import dataclass


@dataclass
class SpotifyTrack:
    """A track from Spotify."""

    uri: str
    id: str
    name: str
    artist: str
    artists: list[str]
    album: str
    duration_ms: int
    popularity: int
    preview_url: str | None = None
    external_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> "SpotifyTrack":
        """Create SpotifyTrack from Spotify API response."""
        artists = [a["name"] for a in data.get("artists", [])]
        return cls(
            uri=data["uri"],
            id=data["id"],
            name=data["name"],
            artist=artists[0] if artists else "Unknown Artist",
            artists=artists,
            album=data.get("album", {}).get("name", ""),
            duration_ms=data.get("duration_ms", 0),
            popularity=data.get("popularity", 0),
            preview_url=data.get("preview_url"),
            external_url=data.get("external_urls", {}).get("spotify"),
        )

    def __str__(self) -> str:
        return f"{self.artist} - {self.name}"


@dataclass
class SpotifyPlaylist:
    """A Spotify playlist."""

    id: str
    name: str
    url: str
    track_count: int
    owner: str

    @classmethod
    def from_api_response(cls, data: dict) -> "SpotifyPlaylist":
        """Create SpotifyPlaylist from Spotify API response."""
        return cls(
            id=data["id"],
            name=data["name"],
            url=data.get("external_urls", {}).get("spotify", ""),
            track_count=data.get("tracks", {}).get("total", 0),
            owner=data.get("owner", {}).get("display_name", ""),
        )
