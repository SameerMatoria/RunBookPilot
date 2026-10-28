"""Impact metrics from the blueprint: conversion rate, time to automate, time saved per run, ROI.

Hours saved per year = sum over runbooks of (manual min - automated min) x runs per year / 60.
Manual minutes and run frequency come from each runbook (extracted by the Parser); automated
minutes is an assumption (an engineer triggers the approved script and checks its output).
"""
from datetime import datetime
from statistics import median

from sqlalchemy import select

from . import store
from .db import session_scope
from .jobs import BUSY_STATUSES
from .models import ScriptRun

AUTOMATED_MINUTES_PER_RUN = 2.0
FINISHED = {"awaiting_approval", "approved", "rejected", "tests_failed", "error"}


def _minutes_between(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60


def _row(record: dict) -> dict:
    parsed = record.get("parsed") or {}
    review = record.get("review")
    passing = next((r for r in reversed(record.get("test_runs", [])) if r.get("passed")), None)
    manual = parsed.get("manual_minutes")
    per_month = parsed.get("runs_per_month")
    row = {
        "id": record["id"],
        "title": parsed.get("title") or record.get("source_file"),
        "risk_tier": parsed.get("risk_tier"),
        "status": record.get("status"),
        "steps": len(parsed.get("steps", [])),
        "questions": sum(1 for s in parsed.get("steps", []) if s.get("ambiguous")),
        "converted": passing is not None,
        "attempts": review["attempts"] if review else len(record.get("test_runs", [])) or None,
        "minutes_to_automate": round(_minutes_between(record["created_at"], review["created_at"]), 1) if review else None,
        "script_seconds": passing["execute"]["duration_s"] if passing else None,
        "manual_minutes": manual,
        "runs_per_month": per_month,
        "hours_saved_per_year": None,
        "speedup": None,
    }
    if passing and isinstance(manual, (int, float)) and isinstance(per_month, (int, float)) and manual > 0:
        saved_per_run = max(manual - AUTOMATED_MINUTES_PER_RUN, 0)
        row["hours_saved_per_year"] = round(saved_per_run * per_month * 12 / 60, 1)
        row["speedup"] = round(manual / AUTOMATED_MINUTES_PER_RUN, 1)
    return row


def measured(records: list[dict]) -> dict:
    """From real runs on servers: how often approved scripts ran, how long they took, time saved."""
    manual = {r["id"]: (r.get("parsed") or {}).get("manual_minutes") for r in records}
    with session_scope() as s:
        runs = [(r.runbook_id, r.status, r.duration_s, r.trigger)
                for r in s.scalars(select(ScriptRun).where(ScriptRun.mode == "execute", ScriptRun.status.in_(("succeeded", "failed"))))]
    succeeded = [r for r in runs if r[1] == "succeeded"]
    saved_minutes, per_runbook = 0.0, {}
    for runbook_id, _, duration, _ in succeeded:
        per_runbook[runbook_id] = per_runbook.get(runbook_id, 0) + 1
        if isinstance(manual.get(runbook_id), (int, float)):
            saved_minutes += max(manual[runbook_id] - (duration or 0) / 60, 0)
    durations = [d for _, _, d, _ in succeeded if d is not None]
    return {
        "execute_runs": len(runs),
        "succeeded": len(succeeded),
        "success_rate": round(len(succeeded) / len(runs) * 100) if runs else None,
        "avg_run_seconds": round(sum(durations) / len(durations), 1) if durations else None,
        "hands_off_runs": sum(1 for r in succeeded if r[3] in ("schedule", "alert")),
        "hours_saved": round(saved_minutes / 60, 1),
        "runs_per_runbook": per_runbook,
    }


def compute() -> dict:
    all_records = store.list_all()
    records = [r for r in all_records if r.get("status") not in BUSY_STATUSES]
    rows = [_row(r) for r in records if r.get("status") in FINISHED]
    converted = [r for r in rows if r["converted"]]
    timed = [r["minutes_to_automate"] for r in converted if r["minutes_to_automate"] is not None]
    return {
        "assumptions": {
            "automated_minutes_per_run": AUTOMATED_MINUTES_PER_RUN,
            "note": "Manual time and frequency come from each runbook. Automated time assumes an engineer "
                    "spends about 2 minutes triggering the approved script and checking its output.",
        },
        "totals": {
            "processed": len(rows),
            "converted": len(converted),
            "first_attempt": sum(1 for r in converted if r["attempts"] == 1),
            "approved": sum(1 for r in rows if r["status"] == "approved"),
            "questions_asked": sum(r["questions"] for r in rows),
            # Median, not mean: one runbook paused for hours (waiting on answers or an AI quota) would dominate a mean.
            "median_minutes_to_automate": round(median(timed), 1) if timed else None,
            "hours_saved_per_year": round(sum(r["hours_saved_per_year"] or 0 for r in converted), 1),
            "manual_runs_per_year": round(sum((r["runs_per_month"] or 0) * 12 for r in converted)),
        },
        "runbooks": rows,
        "measured": measured(all_records),
    }
