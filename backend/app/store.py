"""Tiny JSON-file store for runbooks. Stand-in for Cosmos DB during the MVP."""
import json
import os
import threading
import uuid
from datetime import datetime, timezone

from .config import DATA_DIR

RUNBOOKS_DIR = DATA_DIR / "runbooks"
RUNBOOKS_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(runbook_id: str):
    return RUNBOOKS_DIR / f"{runbook_id}.json"


def create(record: dict) -> dict:
    record = {"id": uuid.uuid4().hex[:12], "created_at": now(), "events": [], **record}
    save(record)
    return record


def save(record: dict) -> None:
    # Write to a temp file and swap it in, so readers never see a half-written file.
    path = _path(record["id"])
    tmp = path.with_suffix(".tmp")
    with _lock:
        tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(tmp, path)


def get(runbook_id: str) -> dict | None:
    path = _path(runbook_id)
    with _lock:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def delete(runbook_id: str) -> None:
    with _lock:
        _path(runbook_id).unlink(missing_ok=True)


def list_all() -> list[dict]:
    with _lock:
        records = [json.loads(p.read_text(encoding="utf-8")) for p in RUNBOOKS_DIR.glob("*.json")]
    return sorted(records, key=lambda r: r["created_at"], reverse=True)


def log(record: dict, agent: str, message: str, level: str = "info") -> None:
    """Append an activity event (shown live in the UI) and persist the record."""
    record.setdefault("events", []).append({"at": now(), "agent": agent, "message": message, "level": level})
    save(record)
