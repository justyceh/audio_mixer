import uuid

from pydantic import BaseModel

from api.schemas.audio import AudioFormat


class ExportRequest(BaseModel):
    project_id: uuid.UUID
    format: AudioFormat = "mp3"
