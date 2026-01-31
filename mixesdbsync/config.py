"""Configuration management using pydantic-settings."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file from current directory or project root
_env_file = Path.cwd() / ".env"
if _env_file.exists():
    load_dotenv(_env_file)


class SpotifyConfig(BaseSettings):
    """Spotify API configuration."""

    model_config = SettingsConfigDict(env_prefix="SPOTIFY_")

    client_id: str = Field(default="", description="Spotify App Client ID")
    client_secret: SecretStr = Field(default=SecretStr(""), description="Spotify App Client Secret")
    redirect_uri: str = Field(
        default="https://localhost",
        description="OAuth redirect URI",
    )

    @property
    def is_configured(self) -> bool:
        """Check if Spotify credentials are configured."""
        return bool(self.client_id and self.client_secret.get_secret_value())


class MatcherConfig(BaseSettings):
    """Track matching configuration."""

    model_config = SettingsConfigDict(env_prefix="MATCHER_")

    min_score: float = Field(
        default=90.0,
        ge=0,
        le=100,
        description="Minimum score to consider a match (strict by default)",
    )
    include_low_confidence: bool = Field(
        default=False,
        description="Include low-confidence matches in playlist",
    )
    artist_weight: float = Field(default=0.4)
    title_weight: float = Field(default=0.6)


class SyncConfig(BaseSettings):
    """Sync behavior configuration."""

    model_config = SettingsConfigDict(env_prefix="SYNC_")

    playlist_public: bool = Field(default=True, description="Create public playlists")
    playlist_prefix: str = Field(default="MixesDB: ", description="Prefix for playlist names")
    update_existing: bool = Field(
        default=True,
        description="Update existing playlists instead of creating new",
    )


class AppConfig(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    spotify: SpotifyConfig = Field(default_factory=SpotifyConfig)
    matcher: MatcherConfig = Field(default_factory=MatcherConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)

    verbose: bool = Field(default=False)
    cache_dir: Path = Field(default=Path.home() / ".mixesdbsync" / "cache")


def load_config() -> AppConfig:
    """Load configuration from environment and .env file."""
    return AppConfig(
        spotify=SpotifyConfig(),
        matcher=MatcherConfig(),
        sync=SyncConfig(),
    )
