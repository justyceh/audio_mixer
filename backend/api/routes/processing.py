"""Background job status and downloads."""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.core.exceptions import ConflictError, NotFoundError
from api.deps import get_current_user, get_db
from api.models import JobStatus
from api.schemas.job import JobOut
from api.services import job_queue, media_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[JobOut])
def list_jobs(status: JobStatus | None = None, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    return job_queue.list_jobs(db, status=status, limit=limit)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Poll this endpoint: status is pending → processing → completed | failed."""
    return job_queue.get_job(db, job_id)


@router.get("/{job_id}/download", response_class=FileResponse)
def download_job_output(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = job_queue.get_job(db, job_id)
    if job.status == JobStatus.failed:
        raise ConflictError("Job failed; there is nothing to download", details={"error": job.error_message})
    if job.status != JobStatus.completed:
        raise ConflictError(f"Job is still {job.status.value}", details={"progress": job.progress})
    if job.output_media_id is None:
        raise NotFoundError("This job does not produce a downloadable file")
    asset = media_service.get_media(db, job.output_media_id)
    path = media_service.media_file_path(asset)
    return FileResponse(path, media_type=asset.mime_type, filename=media_service.disk_filename(asset))
