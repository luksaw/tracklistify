<p align="center">
  <img src="logo.svg" alt="tracklistify" width="200">
</p>

# tracklistify

Sync DJ set tracklists from [MixesDB](https://www.mixesdb.com) to Spotify playlists.

## Features

- Fetches tracklists from MixesDB via their MediaWiki API
- **Strict track matching** - only adds tracks that match exactly (artist, title, remix/version)
- Handles remix/version variations (`(Artist Remix)`, `- Artist Remix`)
- Treats remasters as the same song (better audio, same track)
- Supports artist collaborations (`+`, `&`, `feat`, `ft`, `vs`, etc.)
- Automatically sets playlist cover image from MixesDB artwork
- Dry-run mode to preview matches before creating playlist

## Installation

```bash
cd /path/to/mixesdbsync

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package
pip install -e .
```

## Configuration

### 1. Create a Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Click "Create App"
3. Fill in the app details:
   - App name: `MixesDB Sync`
   - Redirect URI: `http://127.0.0.1:8888/callback`
4. Save and copy your **Client ID** and **Client Secret**

### 2. Set up credentials

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

### 3. Authenticate with Spotify

```bash
mixesdbsync auth
```

This will open a browser window to authorize the app.

## Usage

### Sync a mix to Spotify

```bash
mixesdbsync sync "https://www.mixesdb.com/w/2025-06-06_-_Lukas_Sawicki_-_Off_The_Record,_IDA_Radio"
```

This will:
1. Fetch the tracklist from MixesDB
2. Search for each track on Spotify (strict matching)
3. Create a playlist with matched tracks
4. Set the playlist cover image from MixesDB

### Options

```bash
# Preview matches without creating playlist
mixesdbsync sync "https://www.mixesdb.com/w/..." --dry-run

# Custom playlist name
mixesdbsync sync "https://www.mixesdb.com/w/..." --name "My Custom Playlist"

# Create private playlist
mixesdbsync sync "https://www.mixesdb.com/w/..." --private

# Adjust minimum match score (default: 90, strict)
mixesdbsync sync "https://www.mixesdb.com/w/..." --min-score 85

# Verbose output (show alternatives for unmatched tracks)
mixesdbsync sync "https://www.mixesdb.com/w/..." --verbose
```

### Fetch tracklist only (no Spotify)

Preview a MixesDB tracklist without syncing:

```bash
mixesdbsync fetch "https://www.mixesdb.com/w/2025-06-06_-_Lukas_Sawicki_-_Off_The_Record,_IDA_Radio"
```

### Test Spotify search

Test how well a track matches on Spotify:

```bash
mixesdbsync search "John Talabot" "Mathilda's Dream"
```

### Re-authenticate

Force re-authentication (e.g., after adding new scopes):

```bash
mixesdbsync auth --force
```

## Commands

| Command | Description |
|---------|-------------|
| `mixesdbsync sync <url>` | Sync a tracklist to Spotify |
| `mixesdbsync fetch <url>` | Fetch and display a MixesDB tracklist |
| `mixesdbsync auth` | Authenticate with Spotify |
| `mixesdbsync search <artist> <title>` | Test track search on Spotify |

## How Matching Works

The matcher uses **strict matching** to ensure only correct tracks are added:

1. **Artist matching** (30% weight)
   - All artists from MixesDB must be found in Spotify
   - Handles various collaboration formats (`&`, `+`, `feat`, `ft`, `vs`, etc.)

2. **Title matching** (40% weight)
   - Compares base track titles after removing remix/version info
   - Uses fuzzy matching to handle minor spelling differences

3. **Remix/Version matching** (30% weight)
   - If MixesDB has a remix, Spotify must have the same remix
   - Handles both `(Artist Remix)` and `- Artist Remix` formats
   - Tolerates minor typos in remix artist names
   - **Remasters are ignored** - treated as the same song

Default minimum score is **90%** to ensure high-quality matches.

## Configuration Options

Environment variables (can be set in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SPOTIFY_CLIENT_ID` | - | Spotify app client ID |
| `SPOTIFY_CLIENT_SECRET` | - | Spotify app client secret |
| `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:8888/callback` | OAuth redirect URI |
| `MATCHER_MIN_SCORE` | `90` | Minimum match score (0-100) |
| `SYNC_PLAYLIST_PUBLIC` | `true` | Create public playlists |
| `SYNC_PLAYLIST_PREFIX` | `MixesDB: ` | Prefix for playlist names |

## Project Structure

```
mixesdbsync/
├── mixesdbsync/
│   ├── cli.py              # CLI commands
│   ├── config.py           # Configuration
│   ├── mixesdb/            # MixesDB API client & parser
│   ├── spotify/            # Spotify API client
│   ├── matcher/            # Track matching engine
│   └── sync/               # Sync orchestration
├── .env.example
├── pyproject.toml
└── README.md
```

## License

MIT
