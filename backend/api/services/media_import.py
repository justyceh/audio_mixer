"""Authorized media import from supported sites using yt-dlp.

This is deliberately separate from the editing pipeline: an import just produces a
normal MediaAsset, exactly like a local upload.

Safety rules:
  * URLs pass `validate_import_url` (scheme, allowlisted domain, public IPs only) both
    when the request is made and again inside the worker.
  * yt-dlp's generic extractor (which follows arbitrary links/redirects) is refused, and
    the page URL yt-dlp resolves to must also be on the allowlist.
  * No cookies, credentials or DRM workarounds are used. Content that requires login,
    payment or is DRM-protected fails with a clear error.
"""

import importlib.util
import logging
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from api.core.config import get_settings
from api.core.exceptions import DependencyUnavailableError, ImportRejectedError
from api.models import MediaAsset, MediaSource
from api.services import media_service
from api.utils import ffmpeg
from api.utils.filenames import sanitize_filename
from api.utils.paths import temp_workdir
from api.utils.url_safety import host_matches_allowlist, validate_import_url

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int], None]

_RESTRICTED_HINTS = (
    ("drm", "This media is DRM-protected and cannot be imported"),
    ("sign in", "This media requires signing in and cannot be imported"),
    ("login", "This media requires signing in and cannot be imported"),
    ("private", "This media is private"),
    ("members-only", "This media is restricted to members"),
    ("premium", "This media requires a paid subscription"),
    ("payment", "This media requires payment"),
    ("age-restricted", "This media is age-restricted and cannot be imported without signing in"),
    ("not available in your country", "This media is not available in your region"),
    ("unavailable", "This media is unavailable"),
    ("unsupported url", "This URL is not a supported media page"),
    ("file is larger than max-filesize", "The media exceeds the import size limit"),
)


def check_url(url: str) -> str:
    settings = get_settings()
    if not settings.import_enabled:
        raise ImportRejectedError("URL import is disabled on this server")
    return validate_import_url(url, settings.import_allowed_domains)


def _friendly_error(exc: Exception) -> ImportRejectedError:
    text = str(exc)
    lowered = text.lower()
    for hint, message in _RESTRICTED_HINTS:
        if hint in lowered:
            return ImportRejectedError(message, details=text[-500:])
    return ImportRejectedError("The media could not be downloaded from this URL", details=text[-500:])


def import_from_url(db: Session, url: str, progress: ProgressCallback) -> MediaAsset:
    if importlib.util.find_spec("yt_dlp") is None:
        raise DependencyUnavailableError("yt-dlp is not installed. Install it with: pip install yt-dlp")
    import yt_dlp
    from yt_dlp.utils import DownloadError, ExtractorError

    settings = get_settings()
    url = check_url(url)

    def _hook(status: dict) -> None:
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if total:
                progress(int(status.get("downloaded_bytes", 0) / total * 80))

    with temp_workdir("import") as work:
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[ext=mp4]/best",
            "outtmpl": str(work / "download.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "cachedir": False,
            "max_filesize": settings.import_max_bytes,
            "progress_hooks": [_hook],
            "restrictfilenames": True,
            "windowsfilenames": True,
            "overwrites": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise ImportRejectedError("No media found at this URL")
                if info.get("_type") in ("playlist", "multi_video"):
                    raise ImportRejectedError("Playlists are not supported; import a single video or track")
                if (info.get("extractor_key") or "").lower() == "generic":
                    raise ImportRejectedError("This URL is not a supported media page")
                page_host = (info.get("webpage_url_domain") or "").lower()
                if page_host and not host_matches_allowlist(page_host, settings.import_allowed_domains):
                    raise ImportRejectedError("The URL redirected to an unsupported site")
                if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
                    raise ImportRejectedError("Live streams cannot be imported")
                duration = info.get("duration")
                if duration and duration > settings.import_max_duration_seconds:
                    raise ImportRejectedError(
                        f"Media is longer than the import limit ({settings.import_max_duration_seconds // 60} min)"
                    )
                progress(2)
                info = ydl.process_ie_result(info, download=True)
        except (DownloadError, ExtractorError) as exc:
            raise _friendly_error(exc) from exc

        downloaded = [p for p in work.iterdir() if p.is_file() and p.name.startswith("download.")
                      and not p.name.endswith((".part", ".ytdl"))]
        if not downloaded:
            raise ImportRejectedError("The download did not produce a media file (it may exceed the size limit)")
        path = max(downloaded, key=lambda p: p.stat().st_size)
        progress(85)

        path, ext = _ensure_supported_container(path, work)
        title = sanitize_filename(info.get("title") or "imported media", default="imported media")
        asset = media_service.ingest_file(
            db,
            path,
            original_filename=f"{title}.{ext}",
            source=MediaSource.import_,
            source_url=info.get("webpage_url") or url,
        )
        db.flush()
        return asset


def _ensure_supported_container(path: Path, work: Path) -> tuple[Path, str]:
    ext = path.suffix.lower().lstrip(".")
    if ext in media_service.ALLOWED_EXTENSIONS:
        return path, ext
    # e.g. .opus / .ogg / .mkv: transcode the audio to WAV so it fits the supported set.
    converted = work / "converted.wav"
    ffmpeg.run_ffmpeg(["-i", str(path), "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le", str(converted)])
    return converted, "wav"
