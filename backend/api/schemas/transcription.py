import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    media_id: uuid.UUID
    job_id: uuid.UUID | None
    model: str
    language: str | None
    text: str
    segments: list[TranscriptSegment]
    created_at: datetime
