import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field

from api.models.enums import JobStatus, JobType


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: JobType
    status: JobStatus
    progress: int
    result: dict[str, Any] | None
    input_media_id: uuid.UUID | None
    project_id: uuid.UUID | None
    output_media_id: uuid.UUID | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    updated_at: datetime
    completed_at: datetime | None

    @computed_field
    @property
    def status_url(self) -> str:
        return f"/api/jobs/{self.id}"

    @computed_field
    @property
    def download_url(self) -> str | None:
        if self.status == JobStatus.completed and self.output_media_id is not None:
            return f"/api/jobs/{self.id}/download"
        return None
