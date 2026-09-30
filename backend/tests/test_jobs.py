import uuid

from api.core.exceptions import MediaProcessingError
from api.models import JobStatus, JobType, ProcessingJob
from api.services.job_handlers import JobOutcome
from api.services.job_queue import get_job_queue
from api.worker import process_next_job


def _enqueue(db, job_type=JobType.mix, payload=None) -> uuid.UUID:
    return get_job_queue().enqueue(db, job_type, payload or {}).id


def _status(db, job_id) -> ProcessingJob:
    db.expire_all()
    return db.get(ProcessingJob, job_id)


def test_status_transitions(db, client):
    job_id = _enqueue(db)
    assert _status(db, job_id).status == JobStatus.pending

    seen = {}

    def handler(session, job, progress):
        seen["status_during"] = _status(db, job_id).status
        progress(42)
        seen["progress_during"] = _status(db, job_id).progress
        return JobOutcome(result={"ok": True})

    assert process_next_job({JobType.mix: handler}) == job_id
    job = _status(db, job_id)
    assert seen == {"status_during": JobStatus.processing, "progress_during": 42}
    assert job.status == JobStatus.completed
    assert job.progress == 100
    assert job.result == {"ok": True}
    assert job.started_at is not None and job.completed_at is not None

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "completed"
    assert body["download_url"] is None  # no output media


def test_failed_job_records_error(db, client):
    job_id = _enqueue(db)

    def handler(session, job, progress):
        raise MediaProcessingError("FFmpeg failed to process the media", details="Invalid data found")

    process_next_job({JobType.mix: handler})
    job = _status(db, job_id)
    assert job.status == JobStatus.failed
    assert "FFmpeg failed" in job.error_message and "Invalid data" in job.error_message

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "failed"
    download = client.get(f"/api/jobs/{job_id}/download")
    assert download.status_code == 409


def test_unexpected_exception_marks_failed(db):
    job_id = _enqueue(db)

    def handler(session, job, progress):
        raise RuntimeError("boom")

    process_next_job({JobType.mix: handler})
    job = _status(db, job_id)
    assert job.status == JobStatus.failed and "boom" in job.error_message


def test_download_before_completion_conflicts(db, client):
    job_id = _enqueue(db)
    response = client.get(f"/api/jobs/{job_id}/download")
    assert response.status_code == 409
    assert client.get(f"/api/jobs/{uuid.uuid4()}").status_code == 404


def test_jobs_processed_in_order_and_queue_empty(db):
    first, second = _enqueue(db), _enqueue(db)
    handler = {JobType.mix: lambda s, j, p: JobOutcome()}
    assert process_next_job(handler) == first
    assert process_next_job(handler) == second
    assert process_next_job(handler) is None


def test_stale_processing_jobs_recovered(db):
    from datetime import timedelta

    from api.db.base import utcnow
    from api.services.job_queue import recover_stale_jobs

    job_id = _enqueue(db)
    job = db.get(ProcessingJob, job_id)
    job.status = JobStatus.processing
    job.updated_at = utcnow() - timedelta(hours=5)
    db.commit()
    assert recover_stale_jobs(db, 60) == 1
    assert _status(db, job_id).status == JobStatus.failed
