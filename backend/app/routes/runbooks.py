"""Runbooks: upload, questions, build, retry, approve/reject, delete.

Agent work is queued for the worker. ?wait=true runs it inline and waits (scripts and tests).
"""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from .. import audit, jobqueue, jobs, store
from ..auth import current_user, has_role, require
from ..documents import extract_text

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


@router.post("")
async def upload_runbook(request: Request, file: UploadFile = File(...), wait: bool = False,
                         user: dict = Depends(require("submitter"))):
    content = await file.read()
    try:
        text = extract_text(file.filename or "", content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not text.strip():
        raise HTTPException(400, "No text found in the file.")

    runbook_id = store.create(file.filename or "runbook", text, submitted_by=user["id"])
    store.log(runbook_id, "Engineer", f"{user['display_name']} uploaded {file.filename}")
    audit.record(user, "runbook.upload", "runbook", runbook_id, request, file=file.filename)
    jobs.submit("parse", runbook_id, wait=wait)
    return store.get(runbook_id)


@router.get("")
def list_runbooks(user: dict = Depends(current_user)):
    return store.list_summaries()


@router.get("/{runbook_id}")
def get_runbook(runbook_id: str, user: dict = Depends(current_user)):
    return _load(runbook_id)


@router.delete("/{runbook_id}")
def delete_runbook(runbook_id: str, request: Request, user: dict = Depends(current_user)):
    record = _load_idle(runbook_id)
    if not (has_role(user, "admin") or record["submitted_by"] == user["id"]):
        raise HTTPException(403, "Only the person who uploaded it or an admin can delete a runbook.")
    store.delete_runbook(runbook_id)
    audit.record(user, "runbook.delete", "runbook", runbook_id, request, title=_title(record))
    return {"deleted": runbook_id}


class AnswersIn(BaseModel):
    answers: dict[int, str]  # step order -> engineer's answer


@router.post("/{runbook_id}/answers")
def answer_questions(runbook_id: str, body: AnswersIn, request: Request, wait: bool = False,
                     user: dict = Depends(require("submitter"))):
    """Save the engineer's answers. Once every question is answered, the build starts automatically."""
    record = _load_idle(runbook_id)
    parsed = record.get("parsed") or {}
    for step in parsed.get("steps", []):
        answer = body.answers.get(step["order"])
        if answer and answer.strip():
            step["answer"] = answer.strip()
    store.update(runbook_id, parsed=parsed)
    remaining = jobs.open_questions(parsed)
    store.log(runbook_id, "Engineer", f"{user['display_name']} answered {len(body.answers)} question(s)"
              + (f", {len(remaining)} still open" if remaining else ""))
    audit.record(user, "runbook.answer", "runbook", runbook_id, request, answered=len(body.answers))
    if record["status"] == "needs_answers" and not remaining:
        store.update(runbook_id, status="parsed")
        jobs.submit("build", runbook_id, wait=wait)
    return store.get(runbook_id)


class BuildIn(BaseModel):
    feedback: str | None = None


@router.post("/{runbook_id}/build")
def build(runbook_id: str, request: Request, body: BuildIn | None = None, wait: bool = False,
          user: dict = Depends(require("submitter"))):
    """Author writes the script, Tester tests and fixes it in the sandbox, Reviewer writes the card.
    Pass feedback to regenerate."""
    record = _load_idle(runbook_id)
    if not (record.get("parsed") or {}).get("steps"):
        raise HTTPException(409, "Runbook has not been parsed yet.")
    if questions := jobs.open_questions(record["parsed"]):
        raise HTTPException(409, f"Answer the open questions first (steps {questions}).")
    feedback = body.feedback if body else None
    audit.record(user, "runbook.build", "runbook", runbook_id, request, feedback=feedback)
    jobs.submit("build", runbook_id, wait=wait, feedback=feedback)
    return store.get(runbook_id)


# Blueprint name for "retry with reviewer feedback".
router.post("/{runbook_id}/regenerate")(build)


@router.post("/{runbook_id}/retry")
def retry(runbook_id: str, request: Request, wait: bool = False, user: dict = Depends(require("submitter"))):
    """After an error, continue from where it stopped (e.g. only redo the review if tests passed)."""
    record = _load_idle(runbook_id)
    if record["status"] != "error":
        raise HTTPException(409, f"Nothing to retry (status: {record['status']}).")
    if record.get("parsed") and jobs.open_questions(record["parsed"]):
        store.update(runbook_id, status="needs_answers", error=None)
        return store.get(runbook_id)
    step = jobs.resume_point(record)
    store.update(runbook_id, error=None)
    store.log(runbook_id, "Engineer", f"{user['display_name']} retried from the {step} step")
    audit.record(user, "runbook.retry", "runbook", runbook_id, request, step=step)
    jobs.submit(step, runbook_id, wait=wait)
    return store.get(runbook_id)


class DecisionIn(BaseModel):
    comment: str | None = None


def required_approvals(record: dict) -> int:
    """Risk tiers from the design doc: high-risk scripts need two engineers."""
    return 2 if (record.get("parsed") or {}).get("risk_tier") == "high" else 1


def _check_not_own(record: dict, user: dict) -> None:
    """Separation of duties: nobody approves or rejects their own submission."""
    if record.get("submitted_by") == user["id"]:
        raise HTTPException(403, "You uploaded this runbook, so someone else has to review it.")


@router.post("/{runbook_id}/approve")
def approve(runbook_id: str, request: Request, body: DecisionIn | None = None,
            user: dict = Depends(require("approver"))):
    record = _load_idle(runbook_id)
    if record["status"] != "awaiting_approval":
        raise HTTPException(409, f"Nothing to approve (status: {record['status']}).")
    _check_not_own(record, user)
    comment = body.comment if body else None
    version = record["review"]["script_version"]
    current = [a for a in record["approvals"] if a["script_version"] == version and a["decision"] == "approved"]
    if any(a["user_id"] == user["id"] for a in current):
        raise HTTPException(409, "You have already approved this version; a second engineer is needed.")

    store.add_approval(runbook_id, reviewer=user["display_name"], user_id=user["id"], decision="approved",
                       comment=comment, script_version=version)
    needed = required_approvals(record)
    if len(current) + 1 >= needed:
        store.update(runbook_id, status="approved", approved_version=version)
        store.log(runbook_id, "Engineer", f"{user['display_name']} approved script v{version} - added to the automation library", "success")
    else:
        store.log(runbook_id, "Engineer", f"{user['display_name']} approved ({len(current) + 1} of {needed}); waiting for a second engineer")
    audit.record(user, "runbook.approve", "runbook", runbook_id, request, version=version, comment=comment)
    return store.get(runbook_id)


@router.post("/{runbook_id}/reject")
def reject(runbook_id: str, request: Request, body: DecisionIn | None = None, regenerate: bool = True,
           wait: bool = False, user: dict = Depends(require("approver"))):
    """Reject the script. By default the comment goes back to the Author agent as feedback."""
    record = _load_idle(runbook_id)
    if record["status"] not in ("awaiting_approval", "tests_failed"):
        raise HTTPException(409, f"Nothing to reject (status: {record['status']}).")
    _check_not_own(record, user)
    comment = body.comment if body else None
    version = record["scripts"][-1]["version"]
    store.add_approval(runbook_id, reviewer=user["display_name"], user_id=user["id"], decision="rejected",
                       comment=comment, script_version=version)
    store.update(runbook_id, status="rejected")
    store.log(runbook_id, "Engineer", f"{user['display_name']} rejected v{version}: {comment or 'no comment'}", "warning")
    audit.record(user, "runbook.reject", "runbook", runbook_id, request, version=version, comment=comment)
    if regenerate and comment:
        jobs.submit("build", runbook_id, wait=wait, feedback=f"Reviewer rejected the script: {comment}")
    return store.get(runbook_id)


def _title(record: dict) -> str:
    return (record.get("parsed") or {}).get("title") or record["source_file"]


def _load(runbook_id: str) -> dict:
    record = store.get(runbook_id)
    if not record:
        raise HTTPException(404, "Runbook not found")
    return record


def _load_idle(runbook_id: str) -> dict:
    record = _load(runbook_id)
    if record["status"] in jobs.BUSY_STATUSES or jobqueue.has_active_job(runbook_id):
        raise HTTPException(409, f"Agents are still working on this runbook ({record['status']}).")
    return record
