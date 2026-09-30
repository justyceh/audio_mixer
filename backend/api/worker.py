"""Background worker: `python -m api.worker`

Polls the processing_jobs table, runs one job at a time, and records progress,
results and failures. Run several processes for parallelism.
"""

import argparse
import logging
import signal
import time
import uuid

from api.core.config import get_settings
from api.core.exceptions import AppError
from api.db.session import SessionLocal, get_engine, session_scope
from api.models import JobType
from api.services import job_queue
from api.services.job_handlers import HANDLERS, Handler
from api.utils.paths import ensure_storage_dirs

logger = logging.getLogger("api.worker")

_stop = False


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, AppError):
        message = exc.message
        if exc.details and isinstance(exc.details, str):
            message = f"{message}\n{exc.details}"
        return message
    return f"Unexpected error ({type(exc).__name__}): {exc}"


def execute_job(job_id: uuid.UUID, handlers: dict[JobType, Handler] | None = None) -> None:
    """Run an already-claimed job to completion or failure."""
    handlers = handlers or HANDLERS
    get_engine()
    db = SessionLocal()
    try:
        job = job_queue.get_job(db, job_id)
        handler = handlers.get(job.job_type)
        if handler is None:
            raise AppError(f"No handler registered for job type '{job.job_type.value}'")

        last = {"value": -1, "at": 0.0}

        def progress(value: int) -> None:
            now = time.monotonic()
            if value != last["value"] and (now - last["at"] > 0.5 or value >= 99):
                last.update(value=value, at=now)
                job_queue.set_progress(job_id, value)

        outcome = handler(db, job, progress)
        job_queue.complete_job(db, job, result=_jsonable(outcome.result), output_media_id=outcome.output_media_id)
        logger.info("Job %s (%s) completed", job_id, job.job_type.value)
    except Exception as exc:  # noqa: BLE001 - any failure must be recorded on the job
        db.rollback()
        if isinstance(exc, AppError):
            logger.warning("Job %s failed: %s", job_id, exc.message)
        else:
            logger.exception("Job %s crashed", job_id)
        job_queue.fail_job(job_id, _describe_error(exc))
    finally:
        db.close()


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def process_next_job(handlers: dict[JobType, Handler] | None = None) -> uuid.UUID | None:
    """Claim and run a single pending job. Returns its id, or None if the queue is empty."""
    with session_scope() as db:
        job = job_queue.claim_next_job(db, list((handlers or HANDLERS).keys()))
        job_id = job.id if job else None
    if job_id is None:
        return None
    logger.info("Processing job %s", job_id)
    execute_job(job_id, handlers)
    return job_id


def run_worker(once: bool = False) -> None:
    settings = get_settings()
    ensure_storage_dirs()
    with session_scope() as db:
        recovered = job_queue.recover_stale_jobs(db, settings.worker_stale_job_minutes)
        if recovered:
            logger.warning("Marked %d stale job(s) as failed", recovered)

    def _handle_signal(signum, _frame):
        global _stop
        logger.info("Received signal %s, finishing current job then exiting", signum)
        _stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("Worker started (poll interval %.1fs)", settings.worker_poll_interval_seconds)
    while not _stop:
        try:
            job_id = process_next_job()
        except Exception:  # database hiccup etc. — keep the worker alive
            logger.exception("Worker loop error")
            job_id = None
            time.sleep(5)
        if once and job_id is None:
            break
        if job_id is None:
            time.sleep(settings.worker_poll_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Anime Remix Studio background worker")
    parser.add_argument("--once", action="store_true", help="Process pending jobs, then exit when the queue is empty")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_worker(once=args.once)


if __name__ == "__main__":
    main()
