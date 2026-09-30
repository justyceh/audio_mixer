import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from api.models.enums import TrackType
from api.schemas.media import MediaOut


# --- Clips -----------------------------------------------------------------
class ClipBase(BaseModel):
    timeline_start: float = Field(default=0, ge=0)
    source_start: float = Field(default=0, ge=0)
    source_end: float | None = Field(default=None, gt=0, description="Defaults to the media duration")
    volume: float = Field(default=1.0, ge=0, le=4)
    fade_in: float = Field(default=0, ge=0)
    fade_out: float = Field(default=0, ge=0)


class ClipCreate(ClipBase):
    media_id: uuid.UUID


class ClipUpdate(BaseModel):
    media_id: uuid.UUID | None = None
    track_id: uuid.UUID | None = Field(default=None, description="Move the clip to another track in the same project")
    timeline_start: float | None = Field(default=None, ge=0)
    source_start: float | None = Field(default=None, ge=0)
    source_end: float | None = Field(default=None, gt=0)
    volume: float | None = Field(default=None, ge=0, le=4)
    fade_in: float | None = Field(default=None, ge=0)
    fade_out: float | None = Field(default=None, ge=0)


class ClipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    track_id: uuid.UUID
    media_id: uuid.UUID
    timeline_start: float
    source_start: float
    source_end: float
    volume: float
    fade_in: float
    fade_out: float
    media: MediaOut


# --- Tracks ----------------------------------------------------------------
class TrackCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    track_type: TrackType = TrackType.other
    volume: float = Field(default=1.0, ge=0, le=4)
    muted: bool = False
    order_index: int | None = Field(default=None, ge=0, description="Defaults to after the last track")


class TrackUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    track_type: TrackType | None = None
    volume: float | None = Field(default=None, ge=0, le=4)
    muted: bool | None = None
    order_index: int | None = Field(default=None, ge=0)


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    track_type: TrackType
    volume: float
    muted: bool
    order_index: int
    clips: list[ClipOut]


# --- Projects --------------------------------------------------------------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class ProjectOut(ProjectSummary):
    tracks: list[TrackOut]
    duration: float = Field(description="End of the last clip on the timeline (seconds)")
