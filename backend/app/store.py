"""Data access for runbooks and everything attached to them.

Each function runs in its own short transaction. `get()` returns a plain dict in the shape the API
and web app use (runbook + scripts + test runs + approvals + events).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from .db import session_scope
from .models import Approval, Event, Runbook, ScriptVersion, TestRun, User


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:  # SQLite drops the timezone
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _script_dict(s: ScriptVersion) -> dict:
    return {
        "version": s.version, "created_at": _iso(s.created_at), "author": s.author, "feedback": s.feedback,
        "language": s.language, "script": s.script, "steps": s.steps or [], "notes": s.notes or [], "lint": s.lint,
    }


def _run_dict(r: TestRun) -> dict:
    return {
        "id": r.id, "attempt": r.attempt, "script_version": r.script_version, "started_at": _iso(r.started_at),
        "passed": r.passed, "failed_stage": r.failed_stage, "lint_passed": r.lint_passed,
        "dry_run": r.dry_run, "execute": r.execute, "diagnosis": r.diagnosis,
    }


def _to_dict(rb: Runbook, submitter: User | None = None) -> dict:
    return {
        "id": rb.id,
        "created_at": _iso(rb.created_at),
        "updated_at": _iso(rb.updated_at),
        "source_file": rb.source_file,
        "source_text": rb.source_text,
        "status": rb.status,
        "error": rb.error,
        "parsed": rb.parsed,
        "review": rb.review,
        "approved_version": rb.approved_version,
        "submitted_by": int(rb.submitted_by) if rb.submitted_by else None,
        "submitted_by_name": submitter.display_name if submitter else None,
        "scripts": [_script_dict(s) for s in rb.scripts],
        "test_runs": [_run_dict(r) for r in rb.test_runs],
        "approvals": [
            {"reviewer": a.reviewer, "user_id": a.user_id, "decision": a.decision, "comment": a.comment,
             "script_version": a.script_version, "at": _iso(a.at)}
            for a in rb.approvals
        ],
        "events": [{"at": _iso(e.at), "agent": e.agent, "message": e.message, "level": e.level} for e in rb.events],
    }


# ---------- runbooks ----------

def create(source_file: str, source_text: str, status: str = "uploaded", submitted_by: int | None = None) -> str:
    runbook_id = uuid.uuid4().hex[:12]
    with session_scope() as s:
        s.add(Runbook(id=runbook_id, source_file=source_file, source_text=source_text, status=status,
                      submitted_by=str(submitted_by) if submitted_by else None))
    return runbook_id


def get(runbook_id: str) -> dict | None:
    with session_scope() as s:
        rb = s.get(Runbook, runbook_id)
        if not rb:
            return None
        return _to_dict(rb, s.get(User, int(rb.submitted_by)) if rb.submitted_by else None)


def list_all() -> list[dict]:
    """Full records, newest first (used by metrics)."""
    with session_scope() as s:
        return [_to_dict(rb) for rb in s.scalars(select(Runbook).order_by(Runbook.created_at.desc()))]


def list_summaries() -> list[dict]:
    with session_scope() as s:
        versions = dict(s.execute(select(ScriptVersion.runbook_id, func.count()).group_by(ScriptVersion.runbook_id)).all())
        rows = s.scalars(select(Runbook).order_by(Runbook.created_at.desc())).all()
        return [
            {
                "id": rb.id,
                "title": (rb.parsed or {}).get("title") or rb.source_file,
                "source_file": rb.source_file,
                "status": rb.status,
                "risk_tier": (rb.parsed or {}).get("risk_tier"),
                "steps": len((rb.parsed or {}).get("steps", [])),
                "script_versions": versions.get(rb.id, 0),
                "created_at": _iso(rb.created_at),
            }
            for rb in rows
        ]


def update(runbook_id: str, **fields) -> None:
    """Set top-level fields: status, error, parsed, review, approved_version."""
    with session_scope() as s:
        rb = s.get(Runbook, runbook_id)
        for key, value in fields.items():
            setattr(rb, key, value)


def delete_runbook(runbook_id: str) -> None:
    with session_scope() as s:
        s.execute(delete(Runbook).where(Runbook.id == runbook_id))


# ---------- scripts, test runs, approvals, events ----------

def add_script(runbook_id: str, *, author: str, feedback: str | None, authored: dict, lint: dict) -> dict:
    with session_scope() as s:
        latest = s.scalar(select(func.max(ScriptVersion.version)).where(ScriptVersion.runbook_id == runbook_id)) or 0
        row = ScriptVersion(
            runbook_id=runbook_id, version=latest + 1, author=author, feedback=feedback,
            language=authored.get("language", "bash"), script=authored["script"],
            steps=authored.get("steps", []), notes=authored.get("notes", []), lint=lint,
        )
        s.add(row)
        s.flush()
        return _script_dict(row)


def latest_script(runbook_id: str) -> dict | None:
    with session_scope() as s:
        row = s.scalar(
            select(ScriptVersion).where(ScriptVersion.runbook_id == runbook_id).order_by(ScriptVersion.version.desc()).limit(1)
        )
        return _script_dict(row) if row else None


def add_test_run(runbook_id: str, run: dict) -> int:
    with session_scope() as s:
        row = TestRun(
            runbook_id=runbook_id, attempt=run["attempt"], script_version=run["script_version"],
            passed=run["passed"], failed_stage=run.get("failed_stage"), lint_passed=run["lint_passed"],
            dry_run=run.get("dry_run"), execute=run.get("execute"), diagnosis=run.get("diagnosis"),
        )
        s.add(row)
        s.flush()
        return row.id


def set_diagnosis(test_run_id: int, diagnosis: dict) -> None:
    with session_scope() as s:
        s.get(TestRun, test_run_id).diagnosis = diagnosis


def add_approval(runbook_id: str, *, reviewer: str, decision: str, comment: str | None, script_version: int,
                 user_id: int | None = None) -> None:
    with session_scope() as s:
        s.add(Approval(runbook_id=runbook_id, reviewer=reviewer, user_id=user_id, decision=decision,
                       comment=comment, script_version=script_version))


def log(runbook_id: str, agent: str, message: str, level: str = "info") -> None:
    """Append an activity event (shown live in the web app; also the audit trail)."""
    with session_scope() as s:
        s.add(Event(runbook_id=runbook_id, agent=agent, message=message, level=level))
