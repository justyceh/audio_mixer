"""Audio extraction and trimming with FFmpeg (fast, synchronous operations)."""

import os
import uuid

from sqlalchemy.orm import Session

from api.models import MediaAsset, MediaSource
from api.services import media_service
from api.utils import ffmpeg
from api.utils.paths import new_storage_file


def _fmt_ts(seconds: float) -> str:
    return f"{seconds:.3f}"


def render_audio_segment(src, dst, fmt: str, start: float, end: float, *, full_length: bool) -> None:
    """Write the audio of [start, end) from src to dst in `fmt`. Video streams are dropped."""
    args: list[str] = []
    if start > 0:
        args += ["-ss", _fmt_ts(start)]
    args += ["-i", str(src)]
    if not full_length:
        args += ["-t", _fmt_ts(end - start)]
    args += ["-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1", *ffmpeg.AUDIO_CODEC_ARGS[fmt], str(dst)]
    ffmpeg.run_ffmpeg(args)


def _derive(
    db: Session,
    media_id: uuid.UUID,
    *,
    fmt: str,
    start: float | None,
    end: float | None,
    source: MediaSource,
    label: str,
) -> MediaAsset:
    asset = media_service.get_media(db, media_id)
    media_service.require_audio(asset)
    start_s, end_s = media_service.validate_time_range(start, end, asset.duration)
    full_length = start_s == 0 and end_s >= asset.duration

    src = media_service.media_file_path(asset)
    stored, relative, absolute = new_storage_file("processed", fmt)
    stem = os.path.splitext(asset.original_filename)[0] or "media"
    suffix = label if full_length else f"{label} {start_s:.2f}-{end_s:.2f}"
    with media_service.delete_files_on_error([absolute]):
        render_audio_segment(src, absolute, fmt, start_s, end_s, full_length=full_length)
        new_asset = media_service.register_output(
            db,
            stored_filename=stored,
            relative_path=relative,
            absolute_path=absolute,
            original_filename=f"{stem} ({suffix}).{fmt}",
            source=source,
            parent_media_id=asset.id,
        )
        db.commit()
    db.refresh(new_asset)
    return new_asset


def extract_audio(
    db: Session, media_id: uuid.UUID, fmt: str = "wav", start: float | None = None, end: float | None = None
) -> MediaAsset:
    return _derive(db, media_id, fmt=fmt, start=start, end=end, source=MediaSource.extracted, label="audio")


def trim_audio(db: Session, media_id: uuid.UUID, start: float, end: float, fmt: str = "wav") -> MediaAsset:
    return _derive(db, media_id, fmt=fmt, start=start, end=end, source=MediaSource.trimmed, label="trim")
