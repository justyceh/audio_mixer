"""Test fixtures.

DB-backed tests need TEST_DATABASE_URL (env var or backend/.env) pointing at a
*separate* PostgreSQL database; its tables are dropped and recreated for the run.
Media fixtures are generated with the real FFmpeg binary.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# Isolate storage before any app module reads settings.
_STORAGE = Path(tempfile.mkdtemp(prefix="anime-remix-test-storage-"))
os.environ["STORAGE_ROOT"] = str(_STORAGE)

from api.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from api.db.base import Base  # noqa: E402
from api.db import session as db_session  # noqa: E402
import api.models  # noqa: E402,F401
from api.utils.paths import ensure_storage_dirs  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="FFmpeg/ffprobe not on PATH")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_STORAGE, ignore_errors=True)


@pytest.fixture(scope="session")
def db_engine():
    settings = get_settings()
    url = settings.test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set (see .env.example)")
    if make_url(url) == make_url(settings.database_url):
        pytest.exit("TEST_DATABASE_URL must differ from DATABASE_URL: tests drop all tables", returncode=2)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Test database unreachable: {exc}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db_session.set_engine(engine)
    ensure_storage_dirs()
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_engine):
    session = db_session.SessionLocal()
    yield session
    session.close()
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from api.server import app

    with TestClient(app) as c:
        yield c


# --- Generated media ---------------------------------------------------------
def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory):
    if not HAS_FFMPEG:
        pytest.skip("FFmpeg/ffprobe not on PATH")
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="session")
def wav_file(media_dir) -> Path:
    path = media_dir / "tone.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=3:sample_rate=44100", "-ac", "2", str(path))
    return path


@pytest.fixture(scope="session")
def mp3_file(media_dir) -> Path:
    path = media_dir / "music.mp3"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=4:sample_rate=48000", "-c:a", "libmp3lame", str(path))
    return path


@pytest.fixture(scope="session")
def mp4_file(media_dir) -> Path:
    path = media_dir / "scene.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=660:duration=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    )
    return path


@pytest.fixture
def upload(client):
    def _upload(path: Path, filename: str | None = None, content_type: str = "application/octet-stream"):
        with path.open("rb") as fh:
            return client.post(
                "/api/media/upload", files={"file": (filename or path.name, fh, content_type)}
            )

    return _upload


@pytest.fixture
def uploaded(upload):
    """Upload a file and return the JSON body (asserting success)."""

    def _uploaded(path: Path, filename: str | None = None) -> dict:
        response = upload(path, filename)
        assert response.status_code == 201, response.text
        return response.json()

    return _uploaded
