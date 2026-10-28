"""Agent jobs. The API queues them and a worker process runs them (see worker.py); each reports
progress as events, so the web app can show the agents working live."""
import logging

from . import jobqueue, store
from .agents.author import write_script
from .agents.parser import parse_runbook
from .agents.reviewer import review
from .pipeline import new_script_version, test_and_fix

log = logging.getLogger(__name__)

BUSY_STATUSES = {"queued", "uploaded", "parsing", "writing_script", "testing", "reviewing"}


def open_questions(parsed: dict | None) -> list[int]:
    steps = (parsed or {}).get("steps", [])
    return [s["order"] for s in steps if s.get("ambiguous") and not s.get("answer")]


def submit(kind: str, runbook_id: str, wait: bool = False, **payload) -> None:
    """Queue a job for the worker, or run it right here when wait=True (scripts and tests)."""
    if wait:
        run(kind, runbook_id, payload)
    else:
        store.update(runbook_id, status="queued")
        jobqueue.enqueue(kind, runbook_id, **payload)


def run(kind: str, runbook_id: str, payload: dict) -> str | None:
    """Run one job. A failure marks the runbook as errored (never crashes the worker) and is returned."""
    if kind == "run":
        # Script runs on servers record their own outcome; a failed run doesn't break the runbook.
        from .executor import execute_run

        try:
            execute_run(payload["run_id"])
            return None
        except Exception as e:
            log.exception("Run %s crashed", payload.get("run_id"))
            return str(e)[:500]
    try:
        JOBS[kind](runbook_id, **payload)
        return None
    except Exception as e:
        log.exception("Job %s failed for runbook %s", kind, runbook_id)
        message = str(e)[:500]
        store.update(runbook_id, status="error", error=message)
        store.log(runbook_id, "System", f"Stopped: {message}", "error")
        return message


def parse_job(runbook_id: str) -> None:
    record = store.get(runbook_id)
    store.update(runbook_id, status="parsing")
    store.log(runbook_id, "Parser", f"Reading {record['source_file']}")
    parsed = parse_runbook(record["source_text"])
    questions = open_questions(parsed)
    store.update(runbook_id, parsed=parsed)
    store.log(runbook_id, "Parser", f"Found {len(parsed['steps'])} steps, risk tier {parsed.get('risk_tier')}, "
              f"{len(questions)} question(s) for the engineer", "success")
    if questions:
        store.update(runbook_id, status="needs_answers")
    else:
        build_job(runbook_id)


def build_job(runbook_id: str, feedback: str | None = None) -> None:
    """Author -> lint -> sandbox test/fix loop -> Reviewer."""
    parsed = store.get(runbook_id)["parsed"]
    store.update(runbook_id, status="writing_script", review=None)
    store.log(runbook_id, "Author", "Rewriting the script with reviewer feedback" if feedback else "Writing the script")
    previous = store.latest_script(runbook_id)
    authored = write_script(parsed, feedback=feedback, previous_script=previous["script"] if (feedback and previous) else None)
    script = new_script_version(runbook_id, authored, feedback, author="reviewer_feedback" if feedback else "author")
    store.log(runbook_id, "Author", f"Wrote script v{script['version']} ({len(script['script'].splitlines())} lines)", "success")

    store.update(runbook_id, status="testing")
    summary = test_and_fix(runbook_id, parsed)
    if not summary["passed"]:
        store.update(runbook_id, status="tests_failed")
        return
    review_job(runbook_id)


def review_job(runbook_id: str) -> None:
    """Reviewer writes the card for the latest script, which must have passed its sandbox test."""
    record = store.get(runbook_id)
    final = record["scripts"][-1]
    runs = [r for r in record["test_runs"] if r["script_version"] == final["version"]]
    if not runs or not runs[-1]["passed"]:
        raise RuntimeError(f"Script v{final['version']} has no passing sandbox test to review.")
    attempts = runs[-1]["attempt"]

    store.update(runbook_id, status="reviewing")
    store.log(runbook_id, "Reviewer", "Writing the summary card")
    card = review(record["parsed"], final, runs[-1], attempts)
    store.update(runbook_id, status="awaiting_approval", error=None, review={
        **card, "script_version": final["version"], "attempts": attempts, "created_at": store.now(),
    })
    store.log(runbook_id, "Reviewer", f"Card ready - recommends {card.get('recommendation')} ({card.get('confidence')} confidence)", "success")


def resume_point(record: dict) -> str:
    """Where to pick up after an error: re-parse, rebuild, or just redo the review."""
    if not record.get("parsed"):
        return "parse"
    last_run = record["test_runs"][-1] if record["test_runs"] else None
    if last_run and last_run["passed"] and record["scripts"] and last_run["script_version"] == record["scripts"][-1]["version"]:
        return "review"
    return "build"


JOBS = {"parse": parse_job, "build": build_job, "review": review_job}
