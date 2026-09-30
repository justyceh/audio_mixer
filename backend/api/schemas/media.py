import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field

from api.models.enums import MediaSource, MediaType


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    media_type: MediaType
    source: MediaSource
    format: str
    mime_type: str
    duration: float
    size_bytes: int
    audio_codec: str | None
    sample_rate: int | None
    channels: int | None
    parent_media_id: uuid.UUID | None
    source_url: str | None
    created_at: datetime

    @computed_field
    @property
    def filename(self) -> str:
        return self.original_filename

    @computed_field
    @property
    def url(self) -> str:
        return f"/api/media/{self.id}/stream"


class MediaList(BaseModel):
    items: list[MediaOut]
    total: int
    limit: int
    offset: int


class MediaImportRequest(BaseModel):
    url: HttpUrl = Field(description="Page URL on a supported, authorized source (see IMPORT_ALLOWED_DOMAINS)")
