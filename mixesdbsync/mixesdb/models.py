"""Data models for MixesDB entities."""

from dataclasses import dataclass, field


@dataclass
class MixTrack:
    """A single track from a MixesDB tracklist."""

    position: int
    artist: str
    title: str
    label: str | None = None
    remix: str | None = None

    def __str__(self) -> str:
        result = f"{self.artist} - {self.title}"
        if self.remix:
            result += f" ({self.remix})"
        if self.label:
            result += f" [{self.label}]"
        return result


@dataclass
class Mix:
    """A DJ mix from MixesDB."""

    url: str
    title: str
    tracks: list[MixTrack] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    spotify_url: str | None = None
    soundcloud_url: str | None = None
    image_url: str | None = None

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    def __str__(self) -> str:
        return f"{self.title} ({self.track_count} tracks)"
