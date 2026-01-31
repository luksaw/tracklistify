"""Main sync orchestration engine."""

from dataclasses import dataclass, field

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from mixesdbsync.config import AppConfig, load_config
from mixesdbsync.matcher import MatchResult, TrackMatcher
from mixesdbsync.mixesdb import Mix, MixesDBClient
from mixesdbsync.spotify import SpotifyClient
from mixesdbsync.spotify.models import SpotifyPlaylist


@dataclass
class SyncResult:
    """Result of a sync operation."""

    mix: Mix
    matched_tracks: list[MatchResult] = field(default_factory=list)
    unmatched_tracks: list[MatchResult] = field(default_factory=list)
    playlist: SpotifyPlaylist | None = None
    error: str | None = None

    @property
    def total_tracks(self) -> int:
        return len(self.matched_tracks) + len(self.unmatched_tracks)

    @property
    def match_rate(self) -> float:
        if self.total_tracks == 0:
            return 0.0
        return len(self.matched_tracks) / self.total_tracks

    @property
    def success(self) -> bool:
        return self.error is None and self.playlist is not None


class SyncEngine:
    """Orchestrates the sync process from MixesDB to Spotify."""

    def __init__(self, config: AppConfig | None = None, console: Console | None = None):
        self.config = config or load_config()
        self.console = console or Console()
        self.mixesdb_client = MixesDBClient()
        self._spotify_client: SpotifyClient | None = None
        self._matcher: TrackMatcher | None = None

    @property
    def spotify_client(self) -> SpotifyClient:
        """Lazy-load Spotify client."""
        if self._spotify_client is None:
            self._spotify_client = SpotifyClient(self.config.spotify)
        return self._spotify_client

    @property
    def matcher(self) -> TrackMatcher:
        """Lazy-load track matcher."""
        if self._matcher is None:
            self._matcher = TrackMatcher(self.spotify_client, self.config.matcher)
        return self._matcher

    def fetch_mix(self, url: str) -> Mix:
        """Fetch mix from MixesDB."""
        return self.mixesdb_client.fetch_mix_sync(url)

    def match_tracks(self, mix: Mix, show_progress: bool = True) -> list[MatchResult]:
        """Match all tracks in a mix to Spotify."""
        results: list[MatchResult] = []

        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console,
            ) as progress:
                task = progress.add_task("Matching tracks...", total=len(mix.tracks))

                for track in mix.tracks:
                    result = self.matcher.find_match(track)
                    results.append(result)
                    progress.advance(task)
        else:
            for track in mix.tracks:
                result = self.matcher.find_match(track)
                results.append(result)

        return results

    def create_playlist(
        self,
        mix: Mix,
        matched_results: list[MatchResult],
        custom_name: str | None = None,
        public: bool | None = None,
    ) -> SpotifyPlaylist:
        """Create Spotify playlist from matched tracks."""
        # Determine playlist name
        if custom_name:
            playlist_name = custom_name
        else:
            playlist_name = f"{self.config.sync.playlist_prefix}{mix.title}"

        # Determine visibility
        is_public = public if public is not None else self.config.sync.playlist_public

        # Check for existing playlist if update_existing is enabled
        playlist: SpotifyPlaylist | None = None
        if self.config.sync.update_existing:
            playlist = self.spotify_client.find_existing_playlist(playlist_name)

        if playlist:
            # Clear existing playlist and add new tracks
            self.spotify_client.clear_playlist(playlist.id)
        else:
            # Create new playlist
            description = f"Synced from MixesDB: {mix.url}"
            playlist = self.spotify_client.create_playlist(
                name=playlist_name,
                description=description,
                public=is_public,
            )

        # Add matched tracks
        track_uris = [r.spotify_track.uri for r in matched_results if r.spotify_track]
        if track_uris:
            self.spotify_client.add_tracks_to_playlist(playlist.id, track_uris)

        # Set cover image if available
        if mix.image_url:
            self.spotify_client.set_playlist_cover_image(playlist.id, mix.image_url)

        return playlist

    def sync(
        self,
        url: str,
        playlist_name: str | None = None,
        public: bool | None = None,
        dry_run: bool = False,
    ) -> SyncResult:
        """Perform full sync from MixesDB URL to Spotify playlist."""
        # Fetch mix
        self.console.print(f"[cyan]Fetching mix from MixesDB...[/cyan]")
        try:
            mix = self.fetch_mix(url)
        except Exception as e:
            return SyncResult(
                mix=Mix(url=url, title="Unknown", tracks=[]),
                error=f"Failed to fetch mix: {e}",
            )

        self.console.print(f"[green]Found:[/green] {mix.title}")
        self.console.print(f"[green]Tracks:[/green] {mix.track_count}")

        # Match tracks
        self.console.print()
        results = self.match_tracks(mix)

        # Separate matched and unmatched
        matched = [r for r in results if r.matched]
        unmatched = [r for r in results if not r.matched]

        if dry_run:
            return SyncResult(
                mix=mix,
                matched_tracks=matched,
                unmatched_tracks=unmatched,
                playlist=None,
            )

        # Create playlist
        if matched:
            self.console.print()
            self.console.print("[cyan]Creating Spotify playlist...[/cyan]")
            try:
                playlist = self.create_playlist(mix, matched, playlist_name, public)
            except Exception as e:
                return SyncResult(
                    mix=mix,
                    matched_tracks=matched,
                    unmatched_tracks=unmatched,
                    error=f"Failed to create playlist: {e}",
                )
        else:
            playlist = None

        return SyncResult(
            mix=mix,
            matched_tracks=matched,
            unmatched_tracks=unmatched,
            playlist=playlist,
        )
