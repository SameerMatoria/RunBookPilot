"""Worker heartbeats: workers report whether they're alive and their sandbox works; the API reads it.

The API never talks to Docker itself (in production it can't): sandbox status comes from workers.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from .db import session_scope
from .models import WorkerHeartbeat

ONLINE_WITHIN = timedelta(seconds=90)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def beat(worker_id: str, sandbox_ready: bool, detail: str | None) -> None:
    with session_scope() as s:
        row = s.get(WorkerHeartbeat, worker_id) or WorkerHeartbeat(worker_id=worker_id)
        row.last_seen = _now()
        row.sandbox_ready = sandbox_ready
        row.sandbox_detail = detail
        s.add(row)


def remove(worker_id: str) -> None:
    with session_scope() as s:
        s.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id))


def status() -> dict:
    with session_scope() as s:
        rows = s.scalars(select(WorkerHeartbeat).where(WorkerHeartbeat.last_seen >= _now() - ONLINE_WITHIN)).all()
        if not rows:
            return {"ready": False, "workers": 0, "detail": "No worker is running. Start one with: python -m app.worker"}
        ready = [r for r in rows if r.sandbox_ready]
        return {
            "ready": bool(ready),
            "workers": len(rows),
            "detail": "Sandbox ready" if ready else (rows[0].sandbox_detail or "Sandbox unavailable"),
        }
