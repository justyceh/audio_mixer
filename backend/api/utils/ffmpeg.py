"""Thin, safe wrappers around the ffmpeg / ffprobe executables.

Commands are always passed as argument lists (never through a shell), and failures
surface as MediaProcessingError with the tail of FFmpeg's stderr.
"""

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from api.core.config import get_settings
from api.core.exceptions import DependencyUnavailableError, MediaProcessingError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProbeResult:
    format_names: tuple[str, ...]
    duration: float
    size_bytes: int
    has_video: bool
    audio_codec: str | None
    sample_rate: int | None
    channels: int | None

    @property
    def has_audio(self) -> bool:
        return self.audio_codec is not None


def _binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise DependencyUnavailableError(
            f"'{name}' was not found on PATH. Install FFmpeg and make sure ffmpeg/ffprobe are on PATH "
            "(or set FFMPEG_PATH / FFPROBE_PATH)."
        )
    return path


def ffmpeg_bin() -> str:
    return _binary(get_settings().ffmpeg_path)


def ffprobe_bin() -> str:
    return _binary(get_settings().ffprobe_path)


def ffmpeg_available() -> bool:
    settings = get_settings()
    return shutil.which(settings.ffmpeg_path) is not None and shutil.which(settings.ffprobe_path) is not None


def _stderr_tail(stderr: str | bytes | None, lines: int = 15) -> str:
    if not stderr:
        return ""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    return "\n".join(stderr.strip().splitlines()[-lines:])


def run_ffmpeg(args: list[str], timeout: int | None = None) -> None:
    """Run ffmpeg with the given argument list (inputs, filters, output)."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args]
    logger.debug("Running ffmpeg: %s", cmd)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout or get_settings().ffmpeg_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaProcessingError("FFmpeg timed out") from exc
    if proc.returncode != 0:
        raise MediaProcessingError("FFmpeg failed to process the media", details=_stderr_tail(proc.stderr))


def probe(path: Path) -> ProbeResult:
    cmd = [
        ffprobe_bin(),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        raise MediaProcessingError("ffprobe timed out while inspecting media") from exc
    if proc.returncode != 0:
        raise MediaProcessingError("File is not a readable media file", details=_stderr_tail(proc.stderr))
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError as exc:
        raise MediaProcessingError("ffprobe returned unreadable metadata") from exc

    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    has_video = any(
        s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
        for s in streams
    )

    duration = _to_float(fmt.get("duration"))
    if duration is None and audio is not None:
        duration = _to_float(audio.get("duration"))
    return ProbeResult(
        format_names=tuple(n.strip() for n in (fmt.get("format_name") or "").split(",") if n.strip()),
        duration=duration or 0.0,
        size_bytes=int(fmt.get("size") or path.stat().st_size),
        has_video=has_video,
        audio_codec=audio.get("codec_name") if audio else None,
        sample_rate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        channels=int(audio["channels"]) if audio and audio.get("channels") else None,
    )


def _to_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "N/A") else None
    except (TypeError, ValueError):
        return None


# Output encoders for audio formats we produce.
AUDIO_CODEC_ARGS: dict[str, list[str]] = {
    "wav": ["-c:a", "pcm_s16le"],
    "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
}
