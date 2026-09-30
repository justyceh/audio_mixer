"""Media asset storage, validation and retrieval."""

import logging
import os
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.core.config import get_settings
from api.core.exceptions import (
    ConflictError,
    InvalidTimestampsError,
    MediaProcessingError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaError,
)
from api.models import Clip, MediaAsset, MediaSource, MediaType
from api.utils import ffmpeg
from api.utils.filenames import extension_of, sanitize_filename
from api.utils.paths import new_storage_file, resolve_storage_path, safe_unlink, storage_root

logger = logging.getLogger(__name__)

# extension -> ffprobe format_name token the content must report
ALLOWED_EXTENSIONS: dict[str, str] = {
    "mp3": "mp3",
    "wav": "wav",
    "mp4": "mp4",
    "mov": "mov",
    "m4a": "m4a",
    "webm": "webm",
}

_AUDIO_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "mp4": "audio/mp4", "webm": "audio/webm"}
_VIDEO_MIME = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm", "m4a": "video/mp4"}

# Allowed slack when comparing user timestamps with probed durations.
DURATION_TOLERANCE = 0.05

UPLOAD_CHUNK = 1024 * 1024


def mime_type_for(ext: str, has_video: bool) -> str:
    if has_video:
        return _VIDEO_MIME.get(ext, "application/octet-stream")
    return _AUDIO_MIME.get(ext, "application/octet-stream")


def validate_extension(filename: str) -> str:
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedMediaError(
            f"Unsupported file type '.{ext}'" if ext else "File has no extension",
            details={"allowed": sorted(ALLOWED_EXTENSIONS)},
        )
    return ext


def inspect_media(path: Path, ext: str) -> ffmpeg.ProbeResult:
    """Probe a file and verify its real content matches the claimed extension."""
    try:
        info = ffmpeg.probe(path)
    except MediaProcessingError as exc:
        raise UnsupportedMediaError("File content is not valid audio/video", details=exc.details) from exc
    expected = ALLOWED_EXTENSIONS.get(ext)
    if expected is not None and expected not in info.format_names:
        raise UnsupportedMediaError(
            f"File content does not match the '.{ext}' extension",
            details={"detected_formats": list(info.format_names)},
        )
    if not info.has_audio:
        raise UnsupportedMediaError("Media contains no audio stream")
    if info.duration <= 0:
        raise UnsupportedMediaError("Media has no measurable duration")
    return info


def _create_record(
    db: Session,
    *,
    stored_filename: str,
    relative_path: str,
    absolute_path: Path,
    ext: str,
    info: ffmpeg.ProbeResult,
    original_filename: str,
    source: MediaSource,
    parent_media_id: uuid.UUID | None,
    source_url: str | None,
) -> MediaAsset:
    asset = MediaAsset(
        original_filename=original_filename,
        stored_filename=stored_filename,
        storage_path=relative_path,
        media_type=MediaType.video if info.has_video else MediaType.audio,
        source=source,
        format=ext,
        mime_type=mime_type_for(ext, info.has_video),
        duration=round(info.duration, 3),
        size_bytes=absolute_path.stat().st_size,
        audio_codec=info.audio_codec,
        sample_rate=info.sample_rate,
        channels=info.channels,
        parent_media_id=parent_media_id,
        source_url=source_url,
    )
    db.add(asset)
    db.flush()
    return asset


def ingest_file(
    db: Session,
    src: Path,
    *,
    original_filename: str,
    source: MediaSource,
    area: str = "uploads",
    parent_media_id: uuid.UUID | None = None,
    source_url: str | None = None,
) -> MediaAsset:
    """Validate a file sitting outside the storage areas and move it into `area`.

    Does not commit; the caller owns the transaction. On failure the moved file is removed.
    """
    ext = validate_extension(original_filename)
    info = inspect_media(src, ext)
    stored, relative, absolute = new_storage_file(area, ext)
    shutil.move(str(src), absolute)
    try:
        return _create_record(
            db,
            stored_filename=stored,
            relative_path=relative,
            absolute_path=absolute,
            ext=ext,
            info=info,
            original_filename=original_filename,
            source=source,
            parent_media_id=parent_media_id,
            source_url=source_url,
        )
    except Exception:
        safe_unlink(absolute)
        raise


def register_output(
    db: Session,
    *,
    stored_filename: str,
    relative_path: str,
    absolute_path: Path,
    original_filename: str,
    source: MediaSource,
    parent_media_id: uuid.UUID | None = None,
) -> MediaAsset:
    """Record a file we generated ourselves (already inside a storage area)."""
    ext = extension_of(stored_filename)
    try:
        info = ffmpeg.probe(absolute_path)
    except MediaProcessingError as exc:
        raise MediaProcessingError("Generated output could not be read back", details=exc.details) from exc
    if not info.has_audio or info.duration <= 0:
        raise MediaProcessingError("Generated output contains no audio")
    return _create_record(
        db,
        stored_filename=stored_filename,
        relative_path=relative_path,
        absolute_path=absolute_path,
        ext=ext,
        info=info,
        original_filename=original_filename,
        source=source,
        parent_media_id=parent_media_id,
        source_url=None,
    )


@contextmanager
def delete_files_on_error(paths: list[Path]) -> Iterator[list[Path]]:
    """Remove generated files if the surrounding operation fails."""
    try:
        yield paths
    except BaseException:
        for path in paths:
            safe_unlink(path)
        raise


async def save_upload(db: Session, upload: UploadFile) -> MediaAsset:
    """Stream an upload to storage/temp with a size cap, then validate and store it."""
    from starlette.concurrency import run_in_threadpool

    settings = get_settings()
    original = sanitize_filename(upload.filename)
    ext = validate_extension(original)

    tmp = storage_root() / "temp" / f"upload-{uuid.uuid4().hex}.{ext}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with tmp.open("wb") as fh:
            while chunk := await upload.read(UPLOAD_CHUNK):
                written += len(chunk)
                if written > settings.max_upload_bytes:
                    raise PayloadTooLargeError(f"File exceeds the {settings.max_upload_mb} MB upload limit")
                fh.write(chunk)
        if written == 0:
            raise UnsupportedMediaError("Uploaded file is empty")

        def _ingest() -> MediaAsset:
            asset = ingest_file(db, tmp, original_filename=original, source=MediaSource.upload)
            db.commit()
            db.refresh(asset)
            return asset

        try:
            return await run_in_threadpool(_ingest)
        except Exception:
            db.rollback()
            raise
    finally:
        safe_unlink(tmp)
        await upload.close()


# --- Queries -----------------------------------------------------------------
def get_media(db: Session, media_id: uuid.UUID) -> MediaAsset:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise NotFoundError(f"Media {media_id} not found")
    return asset


def media_file_path(asset: MediaAsset) -> Path:
    path = resolve_storage_path(asset.storage_path)
    if not path.is_file():
        raise NotFoundError(f"File for media {asset.id} is missing from storage")
    return path


def list_media(
    db: Session, *, limit: int = 50, offset: int = 0, media_type: MediaType | None = None,
    source: MediaSource | None = None,
) -> tuple[list[MediaAsset], int]:
    stmt = select(MediaAsset)
    count_stmt = select(func.count()).select_from(MediaAsset)
    if media_type is not None:
        stmt = stmt.where(MediaAsset.media_type == media_type)
        count_stmt = count_stmt.where(MediaAsset.media_type == media_type)
    if source is not None:
        stmt = stmt.where(MediaAsset.source == source)
        count_stmt = count_stmt.where(MediaAsset.source == source)
    items = db.scalars(stmt.order_by(MediaAsset.created_at.desc()).limit(limit).offset(offset)).all()
    total = db.scalar(count_stmt) or 0
    return list(items), total


def delete_media(db: Session, media_id: uuid.UUID) -> None:
    asset = get_media(db, media_id)
    in_use = db.scalar(select(func.count()).select_from(Clip).where(Clip.media_id == media_id))
    if in_use:
        raise ConflictError(
            f"Media is used by {in_use} clip(s) on a project timeline; remove those clips first",
            details={"clip_count": in_use},
        )
    try:
        path = resolve_storage_path(asset.storage_path)
    except Exception:
        path = None
    db.delete(asset)
    db.commit()
    if path is not None:
        safe_unlink(path)


def require_audio(asset: MediaAsset) -> None:
    if not asset.has_audio:
        raise MediaProcessingError(f"Media {asset.id} has no audio stream")


def validate_time_range(
    start: float | None, end: float | None, duration: float
) -> tuple[float, float]:
    """Validate [start, end) against a media duration; returns concrete bounds."""
    start = 0.0 if start is None else float(start)
    end = duration if end is None else float(end)
    if start < 0 or end < 0:
        raise InvalidTimestampsError("Timestamps must be non-negative")
    if start >= duration:
        raise InvalidTimestampsError(
            f"start_time {start} is beyond the media duration ({duration:.3f}s)",
            details={"duration": duration},
        )
    if end > duration + DURATION_TOLERANCE:
        raise InvalidTimestampsError(
            f"end_time {end} exceeds the media duration ({duration:.3f}s)",
            details={"duration": duration},
        )
    end = min(end, duration)
    if end <= start:
        raise InvalidTimestampsError("end_time must be greater than start_time")
    return start, end


def disk_filename(asset: MediaAsset) -> str:
    """Name to offer for downloads: original stem + real extension."""
    stem = os.path.splitext(asset.original_filename)[0] or "media"
    return f"{stem}.{asset.format}"
