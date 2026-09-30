import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

AudioFormat = Literal["wav", "mp3"]


def _check_range(start: float | None, end: float | None) -> None:
    if start is not None and end is not None and end <= start:
        raise ValueError("end_time must be greater than start_time")


class ExtractRequest(BaseModel):
    media_id: uuid.UUID
    format: AudioFormat = "wav"
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate(self):
        _check_range(self.start_time, self.end_time)
        return self


class TrimRequest(BaseModel):
    media_id: uuid.UUID
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)
    format: AudioFormat = "wav"

    @model_validator(mode="after")
    def _validate(self):
        _check_range(self.start_time, self.end_time)
        return self


class IsolateRequest(BaseModel):
    media_id: uuid.UUID
    mode: Literal["vocals", "instrumental"] = "vocals"


class MixTrack(BaseModel):
    media_id: uuid.UUID
    start_time: float = Field(default=0, ge=0, description="Position on the output timeline (seconds)")
    source_start: float = Field(default=0, ge=0)
    source_end: float | None = Field(default=None, gt=0, description="Defaults to the end of the source")
    volume: float = Field(default=1.0, ge=0, le=4)
    fade_in: float = Field(default=0, ge=0)
    fade_out: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate(self):
        if self.source_end is not None and self.source_end <= self.source_start:
            raise ValueError("source_end must be greater than source_start")
        return self


class MixRequest(BaseModel):
    tracks: list[MixTrack] = Field(min_length=1, max_length=64)
    output_format: AudioFormat = "mp3"


class TranscribeRequest(BaseModel):
    media_id: uuid.UUID
    language: str | None = Field(default=None, max_length=8, description="ISO code, e.g. 'ja'. Auto-detect if omitted")
