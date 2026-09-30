"""Background job queue.

The local implementation stores jobs in PostgreSQL (`processing_jobs`) and a separate
worker process (`python -m api.worker`) claims them with `FOR UPDATE SKIP LOCKED`, so
several workers can run safely side by side.

To move to Celery/Redis later: implement `JobQueue.enqueue` to also dispatch a Celery
task carrying the job id, and have that task call `api.worker.execute_job(job_id)`.
The job table stays the source of truth for status polling, so the API doesn't change.
"""

import uuid
from datetime import timedelta
from typing import Any, Protocol

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.core.exceptions import NotFoundError
from api.db.base import utcnow
from api.db.session import session_scope
from api.models import JobStatus, JobType, ProcessingJob


class JobQueue(Protocol):
    def enqueue(
        self,
        db: Session,
        job_type: JobType,
        payload: dict[str, Any],
        *,
        input_media_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> ProcessingJob: ...


class DatabaseJobQueue:
    def enqueue(self, db, job_type, payload, *, input_media_id=None, project_id=None) -> ProcessingJob:
        job = ProcessingJob(
            job_type=job_type,
            status=JobStatus.pending,
            progress=0,
            payload=payload,
            input_media_id=input_media_id,
            project_id=project_id,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job


_queue: JobQueue = DatabaseJobQueue()


def get_job_queue() -> JobQueue:
    return _queue


# --- Read side (API) -----------------------------------------------------------
def get_job(db: Session, job_id: uuid.UUID) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id} not found")
    return job


def list_jobs(db: Session, *, status: JobStatus | None = None, limit: int = 50) -> list[ProcessingJob]:
    stmt = select(ProcessingJob).order_by(ProcessingJob.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(ProcessingJob.status == status)
    return list(db.scalars(stmt).all())


# --- Worker side ---------------------------------------------------------------
def claim_next_job(db: Session, job_types: list[JobType] | None = None) -> ProcessingJob | None:
    """Atomically move the oldest pending job to `processing` and return it."""
    stmt = (
        select(ProcessingJob)
        .where(ProcessingJob.status == JobStatus.pending)
        .order_by(ProcessingJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job_types:
        stmt = stmt.where(ProcessingJob.job_type.in_(job_types))
    job = db.scalars(stmt).first()
    if job is None:
        db.rollback()
        return None
    now = utcnow()
    job.status = JobStatus.processing
    job.started_at = now
    job.updated_at = now
    job.progress = 0
    db.commit()
    db.refresh(job)
    return job


def set_progress(job_id: uuid.UUID, progress: int) -> None:
    """Update progress in its own transaction so pollers see it immediately."""
    progress = max(0, min(int(progress), 99))
    with session_scope() as db:
        db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id, ProcessingJob.status == JobStatus.processing)
            .values(progress=progress, updated_at=utcnow())
        )


def complete_job(
    db: Session, job: ProcessingJob, *, result: dict[str, Any] | None, output_media_id: uuid.UUID | None
) -> None:
    now = utcnow()
    job.status = JobStatus.completed
    job.progress = 100
    job.result = result
    job.output_media_id = output_media_id
    job.error_message = None
    job.completed_at = now
    job.updated_at = now
    db.commit()


def fail_job(job_id: uuid.UUID, message: str) -> None:
    with session_scope() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return
        now = utcnow()
        job.status = JobStatus.failed
        job.error_message = message[:4000]
        job.completed_at = now
        job.updated_at = now


def recover_stale_jobs(db: Session, older_than_minutes: int) -> int:
    """Fail jobs stuck in `processing` (e.g. the worker was killed mid-job)."""
    cutoff = utcnow() - timedelta(minutes=older_than_minutes)
    result = db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.status == JobStatus.processing, ProcessingJob.updated_at < cutoff)
        .values(
            status=JobStatus.failed,
            error_message="Job was interrupted (worker stopped before it finished). Please retry.",
            completed_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    db.commit()
    return result.rowcount or 0
