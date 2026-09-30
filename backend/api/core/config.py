"""Application settings, loaded from environment variables / backend/.env."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Anime Remix Studio API"
    environment: str = "development"

    # Database
    database_url: str = "postgresql+psycopg://anime_remix:change-me@localhost:5432/anime_remix"
    test_database_url: str | None = None
    db_echo: bool = False

    # CORS (comma-separated in .env)
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Storage
    storage_root: Path = BACKEND_DIR / "storage"
    max_upload_mb: int = 500

    # External binaries
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    ffmpeg_timeout_seconds: int = 1800

    # Voice isolation (Demucs)
    demucs_model: str = "htdemucs"
    demucs_device: str = "cpu"
    demucs_timeout_seconds: int = 3600

    # Transcription (faster-whisper)
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # URL import (yt-dlp)
    import_enabled: bool = True
    import_allowed_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "youtube.com",
            "youtu.be",
            "soundcloud.com",
            "vimeo.com",
            "bandcamp.com",
        ]
    )
    import_max_mb: int = 500
    import_max_duration_seconds: int = 3 * 60 * 60

    # Worker
    worker_poll_interval_seconds: float = 1.0
    worker_stale_job_minutes: int = 120

    @field_validator("cors_origins", "import_allowed_domains", mode="before")
    @classmethod
    def _split_csv(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("storage_root", mode="after")
    @classmethod
    def _absolute_storage_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            value = BACKEND_DIR / value
        return value.resolve()

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def import_max_bytes(self) -> int:
        return self.import_max_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
