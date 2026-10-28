"""Job queue stored in Postgres, so no separate message broker is needed (or paid for).

The API enqueues jobs; one or more worker processes claim them with
SELECT ... FOR UPDATE SKIP LOCKED, so two workers never take the same job.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from .db import session_scope
from .models import Job

STALE_AFTER = timedelta(minutes=20)  # a job running longer than this is assumed to have lost its worker


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(kind: str, runbook_id: str, **payload) -> int:
    with session_scope() as s:
        job = Job(kind=kind, runbook_id=runbook_id, payload=payload)
        s.add(job)
        s.flush()
        return job.id


def has_active_job(runbook_id: str) -> bool:
    with session_scope() as s:
        return s.scalar(
            select(Job.id).where(Job.runbook_id == runbook_id, Job.status.in_(("queued", "running"))).limit(1)
        ) is not None


def claim(worker_id: str) -> dict | None:
    """Take the oldest queued job, or return None if there is nothing to do."""
    with session_scope() as s:
        job = s.scalar(
            select(Job)
            .where(Job.status == "queued")
            .order_by(Job.created_at, Job.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status = "running"
        job.locked_by = worker_id
        job.started_at = _now()
        job.attempts += 1
        return {"id": job.id, "kind": job.kind, "runbook_id": job.runbook_id, "payload": job.payload or {}}


def finish(job_id: int, error: str | None = None) -> None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        job.status = "failed" if error else "done"
        job.error = error
        job.finished_at = _now()


def requeue_stale() -> int:
    """Put jobs whose worker died back in the queue. Returns how many were requeued."""
    cutoff = _now() - STALE_AFTER
    with session_scope() as s:
        result = s.execute(
            update(Job)
            .where(Job.status == "running", Job.started_at < cutoff)
            .values(status="queued", locked_by=None)
        )
        return result.rowcount or 0
