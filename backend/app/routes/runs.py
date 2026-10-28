"""Running approved scripts: manual runs, run history, schedules, and alert webhooks."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import audit, runs, store
from ..auth import current_user, require
from ..db import session_scope
from ..models import Schedule, ScriptRun, Server, Trigger

router = APIRouter(tags=["runs"])


def _approved(runbook_id: str) -> dict:
    record = store.get(runbook_id)
    if record is None:
        raise HTTPException(404, "Runbook not found")
    return record


# ---------- manual runs ----------

class RunIn(BaseModel):
    server_ids: list[int]
    mode: str = "dry_run"
    ticket: str | None = None


@router.post("/runbooks/{runbook_id}/runs")
def start_run(runbook_id: str, body: RunIn, request: Request, user: dict = Depends(require("operator"))):
    record = _approved(runbook_id)
    servers = runs.validate_request(record, body.server_ids, body.mode, body.ticket)
    created = runs.create_runs(record, servers, body.mode, body.ticket, user=user)
    audit.record(user, "run.start", "runbook", runbook_id, request, mode=body.mode, ticket=body.ticket,
                 servers=[sv.name for sv in servers], run_ids=[r["id"] for r in created])
    return created


@router.get("/runs")
def list_runs(runbook_id: str | None = None, server_id: int | None = None, status: str | None = None,
              limit: int = 100, user: dict = Depends(current_user)):
    with session_scope() as s:
        query = select(ScriptRun).order_by(ScriptRun.id.desc()).limit(min(limit, 500))
        if runbook_id:
            query = query.where(ScriptRun.runbook_id == runbook_id)
        if server_id:
            query = query.where(ScriptRun.server_id == server_id)
        if status:
            query = query.where(ScriptRun.status == status)
        rows = [runs.run_dict(r) for r in s.scalars(query)]
    titles = {}
    for row in rows:
        if row["runbook_id"] not in titles:
            rec = store.get(row["runbook_id"])
            titles[row["runbook_id"]] = ((rec or {}).get("parsed") or {}).get("title") or (rec or {}).get("source_file")
        row["runbook_title"] = titles[row["runbook_id"]]
    return rows


@router.get("/runs/{run_id}")
def get_run(run_id: int, user: dict = Depends(current_user)):
    with session_scope() as s:
        run = s.get(ScriptRun, run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        data = runs.run_dict(run, include_output=True)
    rec = store.get(data["runbook_id"])
    data["runbook_title"] = ((rec or {}).get("parsed") or {}).get("title")
    data["parsed_steps"] = ((rec or {}).get("parsed") or {}).get("steps", [])
    return data


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, request: Request, user: dict = Depends(require("operator"))):
    with session_scope() as s:
        run = s.get(ScriptRun, run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        if run.status not in ("queued", "running"):
            raise HTTPException(409, f"Run is already {run.status}.")
        run.status = "cancelling"
    audit.record(user, "run.cancel", "run", run_id, request)
    return {"id": run_id, "status": "cancelling"}


# ---------- schedules ----------

def schedule_dict(sc: Schedule) -> dict:
    return {"id": sc.id, "runbook_id": sc.runbook_id, "name": sc.name, "cron": sc.cron, "server_ids": sc.server_ids,
            "mode": sc.mode, "ticket": sc.ticket, "enabled": sc.enabled,
            "next_run_at": sc.next_run_at.isoformat() if sc.next_run_at else None,
            "last_run_at": sc.last_run_at.isoformat() if sc.last_run_at else None}


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    cron: str
    server_ids: list[int]
    mode: str = "execute"
    ticket: str | None = None


@router.get("/runbooks/{runbook_id}/schedules")
def list_schedules(runbook_id: str, user: dict = Depends(current_user)):
    with session_scope() as s:
        return [schedule_dict(sc) for sc in s.scalars(select(Schedule).where(Schedule.runbook_id == runbook_id).order_by(Schedule.id))]


@router.post("/runbooks/{runbook_id}/schedules")
def create_schedule(runbook_id: str, body: ScheduleIn, request: Request, user: dict = Depends(require("operator"))):
    record = _approved(runbook_id)
    runs.validate_request(record, body.server_ids, body.mode, body.ticket)
    with session_scope() as s:
        sc = Schedule(runbook_id=runbook_id, name=body.name, cron=body.cron.strip(), server_ids=body.server_ids,
                      mode=body.mode, ticket=body.ticket, next_run_at=runs.next_time(body.cron.strip()), created_by=user["id"])
        s.add(sc)
        s.flush()
        result = schedule_dict(sc)
    audit.record(user, "run.schedule_create", "runbook", runbook_id, request, schedule=result)
    return result


class ScheduleUpdate(BaseModel):
    enabled: bool | None = None
    cron: str | None = None


@router.patch("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, body: ScheduleUpdate, request: Request, user: dict = Depends(require("operator"))):
    with session_scope() as s:
        sc = s.get(Schedule, schedule_id)
        if sc is None:
            raise HTTPException(404, "Schedule not found")
        if body.cron is not None:
            sc.cron = body.cron.strip()
            sc.next_run_at = runs.next_time(sc.cron)
        if body.enabled is not None:
            sc.enabled = body.enabled
            if body.enabled:
                sc.next_run_at = runs.next_time(sc.cron)
        s.flush()
        result = schedule_dict(sc)
    audit.record(user, "run.schedule_update", "runbook", result["runbook_id"], request, schedule_id=schedule_id,
                 **body.model_dump(exclude_none=True))
    return result


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, request: Request, user: dict = Depends(require("operator"))):
    with session_scope() as s:
        sc = s.get(Schedule, schedule_id)
        if sc is None:
            raise HTTPException(404, "Schedule not found")
        runbook_id = sc.runbook_id
        s.delete(sc)
    audit.record(user, "run.schedule_delete", "runbook", runbook_id, request, schedule_id=schedule_id)
    return {"deleted": schedule_id}


# ---------- alert triggers (webhooks) ----------

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def trigger_dict(t: Trigger) -> dict:
    return {"id": t.id, "runbook_id": t.runbook_id, "name": t.name, "server_ids": t.server_ids, "mode": t.mode,
            "cooldown_minutes": t.cooldown_minutes, "enabled": t.enabled, "url_path": f"/hooks/{t.id}",
            "last_fired_at": t.last_fired_at.isoformat() if t.last_fired_at else None}


class TriggerIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    server_ids: list[int]
    mode: str = "execute"
    cooldown_minutes: int = Field(default=5, ge=0, le=1440)


@router.get("/runbooks/{runbook_id}/triggers")
def list_triggers(runbook_id: str, user: dict = Depends(current_user)):
    with session_scope() as s:
        return [trigger_dict(t) for t in s.scalars(select(Trigger).where(Trigger.runbook_id == runbook_id).order_by(Trigger.id))]


@router.post("/runbooks/{runbook_id}/triggers")
def create_trigger(runbook_id: str, body: TriggerIn, request: Request, user: dict = Depends(require("operator"))):
    record = _approved(runbook_id)
    if body.mode == "execute" and (record.get("parsed") or {}).get("risk_tier") == "high":
        raise HTTPException(400, "High-risk scripts can't be executed automatically from alerts; use dry_run or run them by hand with a ticket.")
    runs.validate_request(record, body.server_ids, body.mode, None)
    token = secrets.token_urlsafe(32)
    with session_scope() as s:
        t = Trigger(runbook_id=runbook_id, name=body.name, server_ids=body.server_ids, mode=body.mode,
                    cooldown_minutes=body.cooldown_minutes, token_hash=_hash(token), created_by=user["id"])
        s.add(t)
        s.flush()
        result = trigger_dict(t)
    audit.record(user, "run.trigger_create", "runbook", runbook_id, request, trigger_id=result["id"], name=body.name)
    return {**result, "token": token}  # shown once; only its hash is stored


@router.delete("/triggers/{trigger_id}")
def delete_trigger(trigger_id: int, request: Request, user: dict = Depends(require("operator"))):
    with session_scope() as s:
        t = s.get(Trigger, trigger_id)
        if t is None:
            raise HTTPException(404, "Trigger not found")
        runbook_id = t.runbook_id
        s.delete(t)
    audit.record(user, "run.trigger_delete", "runbook", runbook_id, request, trigger_id=trigger_id)
    return {"deleted": trigger_id}


class HookIn(BaseModel):
    host: str | None = None  # optional: only run on the server with this name or hostname


@router.post("/hooks/{trigger_id}")
def fire_trigger(trigger_id: int, request: Request, body: HookIn | None = None,
                 x_runbookpilot_token: str = Header(default="")):
    """Called by monitoring tools. Authenticated by the trigger's secret token, not a user session."""
    with session_scope() as s:
        t = s.get(Trigger, trigger_id)
        if t is None or not hmac.compare_digest(t.token_hash, _hash(x_runbookpilot_token or "")):
            raise HTTPException(401, "Unknown trigger or wrong token.")
        if not t.enabled:
            raise HTTPException(409, "This trigger is disabled.")
        now = datetime.now(timezone.utc)
        last = t.last_fired_at.replace(tzinfo=timezone.utc) if t.last_fired_at and t.last_fired_at.tzinfo is None else t.last_fired_at
        if last and now - last < timedelta(minutes=t.cooldown_minutes):
            return {"started": [], "skipped": f"cooling down (fired less than {t.cooldown_minutes} min ago)"}
        server_ids = list(t.server_ids)
        if body and body.host:
            matches = [sv.id for sv in s.scalars(select(Server).where(Server.id.in_(server_ids)))
                       if body.host.lower() in (sv.name.lower(), sv.hostname.lower())]
            if not matches:
                raise HTTPException(404, f"{body.host} is not one of this trigger's servers.")
            server_ids = matches
        t.last_fired_at = now
        runbook_id, mode, name = t.runbook_id, t.mode, t.name
    record = store.get(runbook_id)
    servers = runs.validate_request(record, server_ids, mode, None)
    created = runs.create_runs(record, servers, mode, None, user=None, trigger="alert", trigger_ref=trigger_id)
    audit.record(None, "run.alert", "runbook", runbook_id, request, trigger=name, run_ids=[r["id"] for r in created])
    return {"started": [r["id"] for r in created]}
