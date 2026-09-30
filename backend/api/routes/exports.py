from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from api.models import JobType
from api.schemas.export import ExportRequest
from api.schemas.job import JobOut
from api.services import export_service
from api.services.job_queue import get_job_queue

router = APIRouter(prefix="/api/exports", tags=["exports"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def create_export(body: ExportRequest, db: Session = Depends(get_db)):
    """Render the saved project timeline to MP3/WAV in the background.

    Poll `GET /api/jobs/{job_id}`; when completed, fetch `GET /api/jobs/{job_id}/download`.
    """
    project = export_service.ensure_exportable(db, body.project_id)
    export_service.timeline_inputs(project)  # validate clip bounds / files now
    return get_job_queue().enqueue(
        db, JobType.export, {"project_id": str(project.id), "format": body.format}, project_id=project.id
    )
