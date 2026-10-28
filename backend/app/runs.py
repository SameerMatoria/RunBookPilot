"""Creating script runs (manual, scheduled or alert-triggered) and the scheduler.

Rules enforced for every run, however it was started:
- only the runbook's approved script version runs;
- only enabled servers whose host key has been verified;
- high-risk runbooks need a change ticket for execute runs.
"""
import hashlib
import logging
from datetime import datetime, timezone

from croniter import croniter
from fastapi import HTTPException
from sqlalchemy import select

from . import jobqueue, store
from .db import session_scope
from .models import Schedule, ScriptRun, Server

log = logging.getLogger(__name__)

MODES = ("dry_run", "execute")
FINISHED = ("succeeded", "failed", "cancelled")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_dict(r: ScriptRun, include_output: bool = False) -> dict:
    data = {
        "id": r.id, "runbook_id": r.runbook_id, "script_version": r.script_version, "script_sha256": r.script_sha256,
        "server_id": r.server_id, "server_name": r.server_name, "requested_by": r.requested_by,
        "requested_by_name": r.requested_by_name, "trigger": r.trigger, "trigger_ref": r.trigger_ref,
        "mode": r.mode, "ticket": r.ticket, "status": r.status,
        "queued_at": r.queued_at.isoformat() if r.queued_at else None,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_s": r.duration_s, "exit_code": r.exit_code, "dry_run_passed": r.dry_run_passed,
        "steps": r.steps or [], "error": r.error,
    }
    if include_output:
        data["output"] = r.output or ""
    return data


def validate_request(record: dict, server_ids: list[int], mode: str, ticket: str | None) -> list[Server]:
    """Check a run request against the rules; returns the target servers."""
    if record["status"] != "approved" or not record.get("approved_version"):
        raise HTTPException(409, "Only approved scripts can run on servers.")
    if mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    if mode == "execute" and (record.get("parsed") or {}).get("risk_tier") == "high" and not (ticket or "").strip():
        raise HTTPException(400, "High-risk scripts need a change ticket number to execute.")
    if not server_ids:
        raise HTTPException(400, "Pick at least one server.")
    with session_scope() as s:
        servers = list(s.scalars(select(Server).where(Server.id.in_(server_ids))))
        problems = []
        if missing := set(server_ids) - {sv.id for sv in servers}:
            problems.append(f"unknown server id(s) {sorted(missing)}")
        for sv in servers:
            if not sv.enabled:
                problems.append(f"{sv.name} is disabled")
            elif not sv.host_key:
                problems.append(f"{sv.name} hasn't been verified (run 'Test connection' first)")
            elif not sv.credential_id:
                problems.append(f"{sv.name} has no credential")
        if problems:
            raise HTTPException(400, "Can't run: " + "; ".join(problems))
        s.expunge_all()
        return servers


def create_runs(record: dict, servers: list[Server], mode: str, ticket: str | None, *, user: dict | None,
                trigger: str = "manual", trigger_ref: int | None = None) -> list[dict]:
    version = record["approved_version"]
    script = next(v["script"] for v in record["scripts"] if v["version"] == version)
    sha = hashlib.sha256(script.encode()).hexdigest()
    who = user["display_name"] if user else {"schedule": "Scheduler", "alert": "Alert trigger"}.get(trigger, "System")
    created = []
    with session_scope() as s:
        for server in servers:
            run = ScriptRun(
                runbook_id=record["id"], script_version=version, script_sha256=sha, server_id=server.id,
                server_name=server.name, requested_by=user["id"] if user else None, requested_by_name=who,
                trigger=trigger, trigger_ref=trigger_ref, mode=mode, ticket=(ticket or "").strip() or None,
                status="queued",
            )
            s.add(run)
            s.flush()
            created.append(run_dict(run))
    for run in created:
        jobqueue.enqueue("run", record["id"], run_id=run["id"])
    servers_text = ", ".join(sv.name for sv in servers)
    store.log(record["id"], "Runner", f"{who} queued a {mode.replace('_', ' ')} on {servers_text} ({trigger})")
    return created


# ---------- scheduler ----------

def next_time(cron: str, after: datetime | None = None) -> datetime:
    if not croniter.is_valid(cron):
        raise HTTPException(400, f"'{cron}' is not a valid cron expression (minute hour day month weekday).")
    return croniter(cron, after or _now()).get_next(datetime)


def run_due_schedules() -> int:
    """Start runs for schedules that are due. Safe with several workers (rows are locked)."""
    started = 0
    with session_scope() as s:
        due = list(s.scalars(
            select(Schedule)
            .where(Schedule.enabled.is_(True), Schedule.next_run_at <= _now())
            .with_for_update(skip_locked=True)
        ))
        jobs = []
        for sched in due:
            sched.last_run_at = _now()
            sched.next_run_at = next_time(sched.cron)
            jobs.append((sched.id, sched.runbook_id, list(sched.server_ids), sched.mode, sched.ticket, sched.name))
    for sched_id, runbook_id, server_ids, mode, ticket, name in jobs:
        record = store.get(runbook_id)
        try:
            servers = validate_request(record, server_ids, mode, ticket)
            create_runs(record, servers, mode, ticket, user=None, trigger="schedule", trigger_ref=sched_id)
            started += 1
        except HTTPException as e:
            log.warning("Schedule %s skipped: %s", sched_id, e.detail)
            store.log(runbook_id, "Runner", f"Schedule '{name}' skipped: {e.detail}", "warning")
    return started
