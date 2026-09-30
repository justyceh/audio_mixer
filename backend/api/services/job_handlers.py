"""Job type → handler registry used by the worker.

A handler receives (db, job, progress) and returns a JobOutcome. It must not commit
job status itself — the worker does that — but may commit media records it creates.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from api.models import JobType, MediaSource, ProcessingJob
from api.services import audio_mixer, export_service, media_import, media_service, transcription, voice_isolation

ProgressCallback = Callable[[int], None]


@dataclass
class JobOutcome:
    output_media_id: uuid.UUID | None = None
    result: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Session, ProcessingJob, ProgressCallback], JobOutcome]


def handle_isolate(db: Session, job: ProcessingJob, progress: ProgressCallback) -> JobOutcome:
    asset = media_service.get_media(db, uuid.UUID(job.payload["media_id"]))
    out = voice_isolation.isolate(db, asset, job.payload.get("mode", "vocals"), progress)
    return JobOutcome(output_media_id=out["output_media_id"], result=out["result"])


def handle_mix(db: Session, job: ProcessingJob, progress: ProgressCallback) -> JobOutcome:
    fmt = job.payload.get("output_format", "mp3")
    inputs = audio_mixer.resolve_mix_tracks(db, job.payload["tracks"])
    progress(10)
    asset = audio_mixer.mix_to_asset(
        db, inputs, fmt=fmt, area="processed", original_filename=f"mix.{fmt}", source=MediaSource.mixed
    )
    return JobOutcome(
        output_media_id=asset.id,
        result={"media_id": str(asset.id), "duration": asset.duration, "format": fmt},
    )


def handle_export(db: Session, job: ProcessingJob, progress: ProgressCallback) -> JobOutcome:
    fmt = job.payload.get("format", "mp3")
    progress(5)
    asset = export_service.export_project(db, uuid.UUID(job.payload["project_id"]), fmt)
    return JobOutcome(
        output_media_id=asset.id,
        result={"media_id": str(asset.id), "duration": asset.duration, "format": fmt,
                "filename": asset.original_filename},
    )


def handle_transcribe(db: Session, job: ProcessingJob, progress: ProgressCallback) -> JobOutcome:
    asset = media_service.get_media(db, uuid.UUID(job.payload["media_id"]))
    record = transcription.transcribe_media(db, asset, job.payload.get("language"), progress, job_id=job.id)
    return JobOutcome(
        result={
            "transcription_id": str(record.id),
            "language": record.language,
            "model": record.model,
            "segment_count": len(record.segments),
            "segments": record.segments,
        }
    )


def handle_import(db: Session, job: ProcessingJob, progress: ProgressCallback) -> JobOutcome:
    asset = media_import.import_from_url(db, job.payload["url"], progress)
    return JobOutcome(
        output_media_id=asset.id,
        result={"media_id": str(asset.id), "filename": asset.original_filename, "duration": asset.duration},
    )


HANDLERS: dict[JobType, Handler] = {
    JobType.isolate: handle_isolate,
    JobType.mix: handle_mix,
    JobType.export: handle_export,
    JobType.transcribe: handle_transcribe,
    JobType.import_: handle_import,
}
