"""Projects, tracks and clips (timeline persistence)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from api.core.exceptions import BadRequestError, NotFoundError
from api.db.base import utcnow
from api.models import Clip, MediaAsset, Project, Track
from api.schemas.project import ClipCreate, ClipUpdate, ProjectCreate, ProjectUpdate, TrackCreate, TrackUpdate
from api.services import media_service


def _touch(project: Project) -> None:
    project.updated_at = utcnow()


# --- Projects ----------------------------------------------------------------
def create_project(db: Session, data: ProjectCreate) -> Project:
    project = Project(name=data.name)
    db.add(project)
    db.commit()
    return get_project_full(db, project.id)


def list_projects(db: Session, limit: int = 50, offset: int = 0) -> tuple[list[Project], int]:
    items = db.scalars(select(Project).order_by(Project.updated_at.desc()).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(Project)) or 0
    return list(items), total


def get_project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    return project


def get_project_full(db: Session, project_id: uuid.UUID) -> Project:
    """Project with tracks → clips → media eagerly loaded (one API response)."""
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.tracks).selectinload(Track.clips).joinedload(Clip.media))
        .execution_options(populate_existing=True)
    )
    project = db.scalars(stmt).unique().one_or_none()
    if project is None:
        raise NotFoundError(f"Project {project_id} not found")
    return project


def update_project(db: Session, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
    project = get_project(db, project_id)
    if data.name is not None:
        project.name = data.name
    _touch(project)
    db.commit()
    return get_project_full(db, project_id)


def delete_project(db: Session, project_id: uuid.UUID) -> None:
    project = get_project(db, project_id)
    db.delete(project)
    db.commit()


# --- Tracks ------------------------------------------------------------------
def get_track(db: Session, track_id: uuid.UUID) -> Track:
    track = db.get(Track, track_id)
    if track is None:
        raise NotFoundError(f"Track {track_id} not found")
    return track


def create_track(db: Session, project_id: uuid.UUID, data: TrackCreate) -> Track:
    project = get_project(db, project_id)
    order_index = data.order_index
    if order_index is None:
        current_max = db.scalar(select(func.max(Track.order_index)).where(Track.project_id == project_id))
        order_index = 0 if current_max is None else current_max + 1
    track = Track(
        project_id=project.id,
        name=data.name,
        track_type=data.track_type,
        volume=data.volume,
        muted=data.muted,
        order_index=order_index,
    )
    db.add(track)
    _touch(project)
    db.commit()
    db.refresh(track)
    return track


def update_track(db: Session, track_id: uuid.UUID, data: TrackUpdate) -> Track:
    track = get_track(db, track_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(track, field, value)
    _touch(track.project)
    db.commit()
    db.refresh(track)
    return track


def delete_track(db: Session, track_id: uuid.UUID) -> None:
    track = get_track(db, track_id)
    _touch(track.project)
    db.delete(track)
    db.commit()


# --- Clips -------------------------------------------------------------------
def get_clip(db: Session, clip_id: uuid.UUID) -> Clip:
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise NotFoundError(f"Clip {clip_id} not found")
    return clip


def _validate_clip_bounds(media: MediaAsset, source_start: float, source_end: float | None) -> tuple[float, float]:
    media_service.require_audio(media)
    return media_service.validate_time_range(source_start, source_end, media.duration)


def create_clip(db: Session, track_id: uuid.UUID, data: ClipCreate) -> Clip:
    track = get_track(db, track_id)
    media = media_service.get_media(db, data.media_id)
    start, end = _validate_clip_bounds(media, data.source_start, data.source_end)
    clip = Clip(
        track_id=track.id,
        media_id=media.id,
        timeline_start=data.timeline_start,
        source_start=start,
        source_end=end,
        volume=data.volume,
        fade_in=data.fade_in,
        fade_out=data.fade_out,
    )
    db.add(clip)
    _touch(track.project)
    db.commit()
    db.refresh(clip)
    return clip


def update_clip(db: Session, clip_id: uuid.UUID, data: ClipUpdate) -> Clip:
    clip = get_clip(db, clip_id)
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}

    if "track_id" in changes and changes["track_id"] != clip.track_id:
        target = get_track(db, changes["track_id"])
        if target.project_id != clip.track.project_id:
            raise BadRequestError("Clips can only be moved between tracks of the same project")
        clip.track_id = target.id

    media = clip.media
    if "media_id" in changes and changes["media_id"] != clip.media_id:
        media = media_service.get_media(db, changes["media_id"])
        clip.media_id = media.id
        clip.media = media
        # A new source invalidates the old source range unless both ends are provided.
        changes.setdefault("source_start", 0.0)
        changes.setdefault("source_end", media.duration)

    source_start = changes.get("source_start", clip.source_start)
    source_end = changes.get("source_end", clip.source_end)
    clip.source_start, clip.source_end = _validate_clip_bounds(media, source_start, source_end)

    for field in ("timeline_start", "volume", "fade_in", "fade_out"):
        if field in changes:
            setattr(clip, field, changes[field])

    _touch(clip.track.project)
    db.commit()
    db.refresh(clip)
    return clip


def delete_clip(db: Session, clip_id: uuid.UUID) -> None:
    clip = get_clip(db, clip_id)
    _touch(clip.track.project)
    db.delete(clip)
    db.commit()
