"""One-time import of runbooks saved by the prototype (JSON files in data/) into the database.

Usage:  python -m app.import_json [folder ...]     (default: data/runbooks and data/runbooks-archive)
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR
from .db import session_scope
from .models import Approval, Event, Runbook, ScriptVersion, TestRun


def _dt(value: str | None):
    return datetime.fromisoformat(value) if value else None


def import_record(record: dict) -> bool:
    with session_scope() as s:
        if s.get(Runbook, record["id"]):
            return False
        s.add(Runbook(
            id=record["id"], created_at=_dt(record["created_at"]), source_file=record["source_file"],
            source_text=record["source_text"], status=record["status"], error=record.get("error"),
            parsed=record.get("parsed"), review=record.get("review"), approved_version=record.get("approved_version"),
        ))
        s.flush()
        for v in record.get("scripts", []):
            s.add(ScriptVersion(
                runbook_id=record["id"], version=v["version"], created_at=_dt(v.get("created_at")),
                author=v.get("author") or "author", feedback=v.get("feedback"), language=v.get("language", "bash"),
                script=v["script"], steps=v.get("steps", []), notes=v.get("notes", []), lint=v["lint"],
            ))
        for r in record.get("test_runs", []):
            s.add(TestRun(
                runbook_id=record["id"], attempt=r.get("attempt", 1), script_version=r["script_version"],
                started_at=_dt(r.get("started_at")), passed=r["passed"], failed_stage=r.get("failed_stage"),
                lint_passed=r.get("lint_passed", True), dry_run=r.get("dry_run"), execute=r.get("execute"),
                diagnosis=r.get("diagnosis"),
            ))
        for a in record.get("approvals", []):
            s.add(Approval(runbook_id=record["id"], reviewer=a["reviewer"], decision=a["decision"],
                           comment=a.get("comment"), script_version=a["script_version"], at=_dt(a["at"])))
        for e in record.get("events", []):
            s.add(Event(runbook_id=record["id"], at=_dt(e["at"]), agent=e["agent"], message=e["message"],
                        level=e.get("level", "info")))
    return True


if __name__ == "__main__":
    folders = [Path(a) for a in sys.argv[1:]] or [DATA_DIR / "runbooks", DATA_DIR / "runbooks-archive"]
    imported = skipped = 0
    for folder in folders:
        for path in sorted(folder.glob("*.json")):
            if import_record(json.loads(path.read_text(encoding="utf-8"))):
                imported += 1
            else:
                skipped += 1
    print(f"Imported {imported} runbook(s), skipped {skipped} already in the database.")
