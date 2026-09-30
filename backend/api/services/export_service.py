"""Render a saved project timeline to a single audio file."""

import re
import uuid

from sqlalchemy.orm import Session

from api.core.exceptions import BadRequestError
from api.models import MediaAsset, MediaSource, Project
from api.services import audio_mixer, project_service

MAX_GAIN = 4.0


def timeline_inputs(project: Project) -> list[audio_mixer.MixInput]:
    """Flatten tracks/clips into mixer inputs (muted tracks skipped, gains multiplied)."""
    inputs = []
    for track in project.tracks:
        if track.muted:
            continue
        for clip in track.clips:
            inputs.append(
                audio_mixer.make_mix_input(
                    clip.media,
                    timeline_start=clip.timeline_start,
                    source_start=clip.source_start,
                    source_end=clip.source_end,
                    volume=min(track.volume * clip.volume, MAX_GAIN),
                    fade_in=clip.fade_in,
                    fade_out=clip.fade_out,
                    label=f"track '{track.name}' clip {clip.id}",
                )
            )
    return inputs


def ensure_exportable(db: Session, project_id: uuid.UUID) -> Project:
    project = project_service.get_project_full(db, project_id)
    if not any(clip for track in project.tracks if not track.muted for clip in track.clips):
        raise BadRequestError("Project has no audible clips to export (add clips or unmute a track)")
    return project


def _safe_stem(name: str) -> str:
    stem = re.sub(r"[^\w\- ]+", "_", name).strip() or "export"
    return stem[:100]


def export_project(db: Session, project_id: uuid.UUID, fmt: str) -> MediaAsset:
    project = ensure_exportable(db, project_id)
    inputs = timeline_inputs(project)
    return audio_mixer.mix_to_asset(
        db,
        inputs,
        fmt=fmt,
        area="exports",
        original_filename=f"{_safe_stem(project.name)}.{fmt}",
        source=MediaSource.export,
    )
