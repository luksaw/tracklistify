"""Command-line interface for MixesDB sync."""

from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from mixesdbsync.config import load_config
from mixesdbsync.matcher import MatchConfidence
from mixesdbsync.sync import SyncEngine

app = typer.Typer(
    name="mixesdbsync",
    help="Sync DJ set tracklists from MixesDB to Spotify playlists.",
    no_args_is_help=True,
)
console = Console()


def confidence_color(confidence: MatchConfidence) -> str:
    """Get color for confidence level."""
    return {
        MatchConfidence.EXACT: "green",
        MatchConfidence.HIGH: "green",
        MatchConfidence.MEDIUM: "yellow",
        MatchConfidence.LOW: "red",
        MatchConfidence.NO_MATCH: "dim",
    }.get(confidence, "white")


@app.command()
def sync(
    url: Annotated[str, typer.Argument(help="MixesDB mix URL to sync")],
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Custom playlist name"),
    ] = None,
    public: Annotated[
        bool,
        typer.Option("--public/--private", help="Create public or private playlist"),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-d", help="Preview matches without creating playlist"),
    ] = False,
    min_score: Annotated[
        float,
        typer.Option("--min-score", "-s", help="Minimum match confidence score (0-100)"),
    ] = 90.0,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed match info"),
    ] = False,
) -> None:
    """Sync a MixesDB tracklist to a Spotify playlist."""
    config = load_config()
    config.matcher.min_score = min_score

    engine = SyncEngine(config=config, console=console)

    try:
        result = engine.sync(url, playlist_name=name, public=public, dry_run=dry_run)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if result.error:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(1)

    # Display results
    console.print()

    # Matched tracks table
    if result.matched_tracks:
        table = Table(title="Matched Tracks", show_lines=False)
        table.add_column("#", style="dim", width=3)
        table.add_column("MixesDB", style="cyan")
        table.add_column("Spotify", style="green")
        table.add_column("Score", justify="right", width=6)

        for r in result.matched_tracks:
            track = r.mixesdb_track
            spotify = r.spotify_track
            color = confidence_color(r.confidence)
            table.add_row(
                str(track.position),
                f"{track.artist} - {track.title}",
                f"{spotify.artist} - {spotify.name}" if spotify else "-",
                f"[{color}]{r.score:.0f}%[/{color}]",
            )

        console.print(table)

    # Unmatched tracks
    if result.unmatched_tracks:
        console.print()
        console.print("[red]Unmatched Tracks:[/red]")
        for r in result.unmatched_tracks:
            track = r.mixesdb_track
            console.print(f"  [dim]{track.position}.[/dim] {track.artist} - {track.title}")

            if verbose and r.alternatives:
                console.print("    [dim]Alternatives:[/dim]")
                for alt in r.alternatives[:3]:
                    console.print(f"      - {alt.artist} - {alt.name}")

    # Summary
    console.print()
    console.print(
        f"[bold]Summary:[/bold] {len(result.matched_tracks)}/{result.total_tracks} "
        f"tracks matched ({result.match_rate:.0%})"
    )

    if dry_run:
        console.print("[yellow]Dry run - no playlist created[/yellow]")
    elif result.playlist:
        console.print(f"[green]Playlist created:[/green] {result.playlist.url}")


@app.command()
def auth(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force re-authentication"),
    ] = False,
) -> None:
    """Authenticate with Spotify."""
    from pathlib import Path

    from mixesdbsync.spotify.client import SpotifyClient

    config = load_config()

    if not config.spotify.is_configured:
        console.print("[red]Spotify credentials not configured.[/red]")
        console.print()
        console.print("Set these environment variables or create a .env file:")
        console.print("  SPOTIFY_CLIENT_ID=your_client_id")
        console.print("  SPOTIFY_CLIENT_SECRET=your_client_secret")
        console.print()
        console.print("Get credentials at: https://developer.spotify.com/dashboard")
        raise typer.Exit(1)

    cache_path = Path.home() / ".mixesdbsync" / ".spotify_cache"

    if force and cache_path.exists():
        cache_path.unlink()
        console.print("[yellow]Cleared existing token cache[/yellow]")

    console.print("[cyan]Authenticating with Spotify...[/cyan]")
    console.print("[dim]A browser window will open for authorization.[/dim]")

    try:
        client = SpotifyClient(config.spotify, cache_path)
        client.authenticate()
        user = client.get_current_user()
        console.print()
        console.print(f"[green]Authenticated as:[/green] {user['display_name']}")
        console.print(f"[green]User ID:[/green] {user['id']}")
    except Exception as e:
        console.print(f"[red]Authentication failed:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def search(
    artist: Annotated[str, typer.Argument(help="Artist name")],
    title: Annotated[str, typer.Argument(help="Track title")],
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Number of results"),
    ] = 5,
) -> None:
    """Test track search on Spotify."""
    from mixesdbsync.spotify.client import SpotifyClient

    config = load_config()

    if not config.spotify.is_configured:
        console.print("[red]Spotify credentials not configured.[/red]")
        console.print("Run 'mixesdbsync auth' first.")
        raise typer.Exit(1)

    client = SpotifyClient(config.spotify)

    console.print(f"[cyan]Searching for:[/cyan] {artist} - {title}")
    console.print()

    # Try exact search first
    console.print("[dim]Exact search:[/dim]")
    results = client.search_track_exact(artist, title, limit)
    if results:
        for i, track in enumerate(results, 1):
            console.print(f"  {i}. {track.artist} - {track.name}")
            console.print(f"     [dim]Album: {track.album}[/dim]")
    else:
        console.print("  [dim]No results[/dim]")

    console.print()

    # Try general search
    console.print("[dim]General search:[/dim]")
    results = client.search_track_general(artist, title, limit)
    if results:
        for i, track in enumerate(results, 1):
            console.print(f"  {i}. {track.artist} - {track.name}")
            console.print(f"     [dim]Album: {track.album}[/dim]")
    else:
        console.print("  [dim]No results[/dim]")


@app.command()
def fetch(
    url: Annotated[str, typer.Argument(help="MixesDB mix URL")],
) -> None:
    """Fetch and display a MixesDB tracklist (no Spotify required)."""
    from mixesdbsync.mixesdb import MixesDBClient

    client = MixesDBClient()

    console.print(f"[cyan]Fetching:[/cyan] {url}")
    console.print()

    try:
        mix = client.fetch_mix_sync(url)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold]{mix.title}[/bold]")
    console.print(f"[dim]Tracks: {mix.track_count}[/dim]")

    if mix.categories:
        console.print(f"[dim]Categories: {', '.join(mix.categories)}[/dim]")

    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("Artist", style="cyan")
    table.add_column("Title")
    table.add_column("Label", style="dim")

    for track in mix.tracks:
        table.add_row(
            str(track.position),
            track.artist,
            track.title,
            track.label or "",
        )

    console.print(table)

    if mix.spotify_url:
        console.print()
        console.print(f"[dim]Spotify:[/dim] {mix.spotify_url}")
    if mix.soundcloud_url:
        console.print(f"[dim]SoundCloud:[/dim] {mix.soundcloud_url}")


if __name__ == "__main__":
    app()
