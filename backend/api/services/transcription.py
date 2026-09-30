"""Timestamped speech transcription with faster-whisper (local inference)."""

import importlib.util
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from api.core.config import get_settings
from api.core.exceptions import DependencyUnavailableError
from api.models import MediaAsset, Transcription
from api.services import media_service
from api.utils import ffmpeg
from api.utils.paths import temp_workdir

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int], None]


@dataclass
class TranscriptResult:
    language: str | None
    segments: list[dict]  # {"start", "end", "text"}

    @property
    def text(self) -> str:
        return " ".join(seg["text"] for seg in self.segments).strip()


class Transcriber(Protocol):
    name: str

    def transcribe(self, audio_path: Path, language: str | None, duration: float,
                   progress: ProgressCallback) -> TranscriptResult: ...


class FasterWhisperTranscriber:
    def __init__(self, model: str, device: str, compute_type: str):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.name = f"faster-whisper:{model}"
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if importlib.util.find_spec("faster_whisper") is None:
            raise DependencyUnavailableError("faster-whisper is not installed. Install it with: pip install faster-whisper")
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                logger.info("Loading Whisper model %s on %s (%s)", self.model_name, self.device, self.compute_type)
                self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        return self._model

    def transcribe(self, audio_path: Path, language: str | None, duration: float,
                   progress: ProgressCallback) -> TranscriptResult:
        model = self._load()
        segments_iter, info = model.transcribe(str(audio_path), language=language, vad_filter=True)
        segments = []
        for seg in segments_iter:  # generator: decoding happens while iterating
            segments.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()})
            if duration > 0:
                progress(min(int(seg.end / duration * 100), 99))
        return TranscriptResult(language=info.language, segments=segments)


_transcriber: Transcriber | None = None


def get_transcriber() -> Transcriber:
    """One model instance per process (loading Whisper is expensive)."""
    global _transcriber
    if _transcriber is None:
        settings = get_settings()
        _transcriber = FasterWhisperTranscriber(
            settings.whisper_model, settings.whisper_device, settings.whisper_compute_type
        )
    return _transcriber


def transcribe_media(
    db: Session,
    asset: MediaAsset,
    language: str | None,
    progress: ProgressCallback,
    job_id=None,
    transcriber: Transcriber | None = None,
) -> Transcription:
    media_service.require_audio(asset)
    transcriber = transcriber or get_transcriber()
    src = media_service.media_file_path(asset)
    with temp_workdir("transcribe") as work:
        wav = work / "speech.wav"
        ffmpeg.run_ffmpeg(["-i", str(src), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                           "-c:a", "pcm_s16le", str(wav)])
        progress(5)
        result = transcriber.transcribe(wav, language, asset.duration, lambda p: progress(5 + int(p * 0.9)))

    record = Transcription(
        media_id=asset.id,
        job_id=job_id,
        model=transcriber.name,
        language=result.language,
        text=result.text,
        segments=result.segments,
    )
    db.add(record)
    db.flush()
    return record
