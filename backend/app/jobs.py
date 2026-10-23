"""Agent jobs. Each runs in a background thread and reports progress through the record's events,
so the web app can show the agents working live. Pass wait=True to run inline (scripts, tests)."""
import threading
import traceback

from . import store
from .agents.author import write_script
from .agents.parser import parse_runbook
from .agents.reviewer import review
from .pipeline import new_script_version, test_and_fix

BUSY_STATUSES = {"parsing", "writing_script", "testing", "reviewing"}


def open_questions(record: dict) -> list[int]:
    steps = (record.get("parsed") or {}).get("steps", [])
    return [s["order"] for s in steps if s.get("ambiguous") and not s.get("answer")]


def start(job, runbook_id: str, wait: bool = False, **kwargs) -> None:
    if wait:
        _guarded(job, runbook_id, **kwargs)
    else:
        threading.Thread(target=_guarded, args=(job, runbook_id), kwargs=kwargs, daemon=True).start()


def _guarded(job, runbook_id: str, **kwargs) -> None:
    record = store.get(runbook_id)
    try:
        job(record, **kwargs)
    except Exception as e:
        traceback.print_exc()
        record["status"] = "error"
        record["error"] = str(e)
        store.log(record, "System", f"Stopped: {e}", "error")


def parse_job(record: dict) -> None:
    record["status"] = "parsing"
    store.log(record, "Parser", f"Reading {record['source_file']}")
    record["parsed"] = parse_runbook(record["source_text"])
    steps = record["parsed"]["steps"]
    questions = open_questions(record)
    store.log(record, "Parser", f"Found {len(steps)} steps, risk tier {record['parsed'].get('risk_tier')}, "
              f"{len(questions)} question(s) for the engineer", "success")
    if questions:
        record["status"] = "needs_answers"
        store.save(record)
    else:
        build_job(record)


def build_job(record: dict, feedback: str | None = None) -> None:
    """Author -> lint -> sandbox test/fix loop -> Reviewer."""
    record["status"] = "writing_script"
    record.pop("review", None)
    store.log(record, "Author", "Rewriting the script with reviewer feedback" if feedback else "Writing the script")
    previous = record["scripts"][-1]["script"] if record.get("scripts") else None
    authored = write_script(record["parsed"], feedback=feedback, previous_script=previous if feedback else None)
    script = new_script_version(record, authored, feedback, author="reviewer_feedback" if feedback else "author")
    store.log(record, "Author", f"Wrote script v{script['version']} ({len(script['script'].splitlines())} lines)", "success")

    record["status"] = "testing"
    store.save(record)
    summary = test_and_fix(record)
    if not summary["passed"]:
        record["status"] = "tests_failed"
        store.save(record)
        return

    record["status"] = "reviewing"
    store.log(record, "Reviewer", "Writing the summary card")
    final = record["scripts"][-1]
    card = review(record["parsed"], final, summary["run"], summary["attempts"])
    record["review"] = {**card, "script_version": final["version"], "attempts": summary["attempts"], "created_at": store.now()}
    record["status"] = "awaiting_approval"
    store.log(record, "Reviewer", f"Card ready - recommends {card.get('recommendation')} ({card.get('confidence')} confidence)", "success")
