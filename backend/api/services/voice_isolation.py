"""AI source separation (voice isolation).

The default backend is Demucs (htdemucs, two-stem mode: vocals / no_vocals), run
locally in a subprocess. Demucs is trained for *music* source separation: on anime
scenes it separates voices from the score reasonably well, but sound effects, ambience
and crowd noise can end up in either stem. The output must not be presented as
guaranteed clean dialogue.

New models (speech enhancement, dialogue/SFX separators, ...) can be added by
implementing `SeparationBackend` and registering it in `BACKENDS`.
"""

import importlib.util
import logging
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from api.core.config import get_settings
from api.core.exceptions import DependencyUnavailableError, MediaProcessingError
from api.models import MediaAsset, MediaSource
from api.services import media_service
from api.utils import ffmpeg
from api.utils.paths import new_storage_file, temp_workdir

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int], None]

SEPARATION_NOTE = (
    "Separated with Demucs, a music source-separation model. Voices are isolated from the "
    "background music, but sound effects and ambience may remain in the vocal stem."
)


class SeparationBackend(Protocol):
    name: str

    def separate(self, input_wav: Path, workdir: Path, progress: ProgressCallback) -> dict[str, Path]:
        """Return {"vocals": path, "instrumental": path} for the input file."""
        ...


class DemucsBackend:
    """Runs `python -m demucs --two-stems vocals` in a subprocess."""

    _PERCENT = re.compile(rb"(\d{1,3})%\|")

    def __init__(self, model: str, device: str, timeout: int):
        self.model = model
        self.device = device
        self.timeout = timeout
        self.name = f"demucs:{model}"

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("demucs") is not None

    def separate(self, input_wav: Path, workdir: Path, progress: ProgressCallback) -> dict[str, Path]:
        if not self.available():
            raise DependencyUnavailableError(
                "Demucs is not installed in this environment. Install it with: pip install demucs "
                "(see README for the PyTorch CPU install)."
            )
        out_dir = workdir / "demucs"
        cmd = [
            sys.executable, "-m", "demucs",
            "--two-stems", "vocals",
            "-n", self.model,
            "-d", self.device,
            "-o", str(out_dir),
            str(input_wav),
        ]
        logger.info("Running Demucs: %s", cmd)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)

        stderr_buf = bytearray()
        state = {"percent": 0}

        def _reader() -> None:
            assert proc.stderr is not None
            while chunk := proc.stderr.read(512):
                stderr_buf.extend(chunk)
                matches = self._PERCENT.findall(chunk)
                if matches:
                    state["percent"] = min(int(matches[-1]), 100)

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()
        deadline = time.monotonic() + self.timeout
        last_reported = -1
        while True:
            try:
                proc.wait(timeout=2)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() > deadline:
                    proc.kill()
                    proc.wait()
                    raise MediaProcessingError("Voice isolation timed out")
                if state["percent"] != last_reported:
                    last_reported = state["percent"]
                    progress(last_reported)
        reader.join(timeout=5)

        if proc.returncode != 0:
            tail = "\n".join(bytes(stderr_buf).decode("utf-8", errors="replace").strip().splitlines()[-15:])
            raise MediaProcessingError("Demucs failed to separate the audio", details=tail)

        stem_dir = out_dir / self.model / input_wav.stem
        stems = {"vocals": stem_dir / "vocals.wav", "instrumental": stem_dir / "no_vocals.wav"}
        missing = [name for name, path in stems.items() if not path.is_file()]
        if missing:
            raise MediaProcessingError(f"Demucs did not produce the expected stems: {missing}")
        return stems


def get_separation_backend() -> SeparationBackend:
    settings = get_settings()
    return DemucsBackend(settings.demucs_model, settings.demucs_device, settings.demucs_timeout_seconds)


def isolate(
    db: Session,
    asset: MediaAsset,
    mode: str,
    progress: ProgressCallback,
    backend: SeparationBackend | None = None,
) -> dict:
    """Separate `asset` into vocal + accompaniment stems and store both as new media.

    Returns a job result dict. The job's primary output is the stem named by `mode`.
    """
    media_service.require_audio(asset)
    backend = backend or get_separation_backend()
    src = media_service.media_file_path(asset)
    stem_name = os.path.splitext(asset.original_filename)[0] or "media"

    with temp_workdir("isolate") as work:
        # Normalize any container/codec into a 44.1 kHz stereo WAV for the model.
        prepared = work / "input.wav"
        ffmpeg.run_ffmpeg(["-i", str(src), "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "44100",
                           "-c:a", "pcm_s16le", str(prepared)])
        progress(5)

        stems = backend.separate(prepared, work, lambda pct: progress(5 + int(pct * 0.85)))
        progress(92)

        created: list[Path] = []
        assets: dict[str, MediaAsset] = {}
        with media_service.delete_files_on_error(created):
            for key, label in (("vocals", "vocals"), ("instrumental", "instrumental")):
                stored, relative, absolute = new_storage_file("processed", "wav")
                created.append(absolute)
                # Re-encode to 16-bit PCM regardless of what the backend wrote.
                ffmpeg.run_ffmpeg(["-i", str(stems[key]), "-c:a", "pcm_s16le", str(absolute)])
                assets[key] = media_service.register_output(
                    db,
                    stored_filename=stored,
                    relative_path=relative,
                    absolute_path=absolute,
                    original_filename=f"{stem_name} ({label}).wav",
                    source=MediaSource.isolated,
                    parent_media_id=asset.id,
                )
            db.flush()

    primary = assets["vocals" if mode == "vocals" else "instrumental"]
    return {
        "output_media_id": primary.id,
        "result": {
            "mode": mode,
            "backend": backend.name,
            "vocals_media_id": str(assets["vocals"].id),
            "instrumental_media_id": str(assets["instrumental"].id),
            "note": SEPARATION_NOTE,
        },
    }
