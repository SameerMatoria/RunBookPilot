"""RunbookPilot backend API.

Agent work (parse, write, test, review) runs in the background; poll GET /runbooks/{id} for status
and the live activity log. Add ?wait=true to block until the job finishes (used by scripts/tests).
"""
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, jobs, sandbox, store
from .documents import extract_text

app = FastAPI(title="RunbookPilot API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {
        "ok": True,
        "model": config.LLM_MODEL,
        "key_configured": bool(config.LLM_API_KEY),
        "fallback_model": config.LLM_FALLBACK_MODEL if config.LLM_FALLBACK_API_KEY else None,
    }


@app.get("/sandbox")
def sandbox_status():
    return sandbox.status()


@app.post("/runbooks")
async def upload_runbook(file: UploadFile = File(...), wait: bool = False):
    content = await file.read()
    try:
        text = extract_text(file.filename or "", content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not text.strip():
        raise HTTPException(400, "No text found in the file.")

    record = store.create({"source_file": file.filename, "source_text": text, "status": "uploaded"})
    store.log(record, "System", f"Uploaded {file.filename}")
    jobs.start(jobs.parse_job, record["id"], wait=wait)
    return store.get(record["id"])


@app.get("/runbooks")
def list_runbooks():
    return [
        {
            "id": r["id"],
            "title": (r.get("parsed") or {}).get("title") or r.get("source_file"),
            "source_file": r.get("source_file"),
            "status": r.get("status"),
            "risk_tier": (r.get("parsed") or {}).get("risk_tier"),
            "steps": len((r.get("parsed") or {}).get("steps", [])),
            "script_versions": len(r.get("scripts", [])),
            "created_at": r.get("created_at"),
        }
        for r in store.list_all()
    ]


@app.get("/runbooks/{runbook_id}")
def get_runbook(runbook_id: str):
    return _load(runbook_id)


@app.delete("/runbooks/{runbook_id}")
def delete_runbook(runbook_id: str):
    _load(runbook_id)
    store.delete(runbook_id)
    return {"deleted": runbook_id}


class AnswersIn(BaseModel):
    answers: dict[int, str]  # step order -> engineer's answer


@app.post("/runbooks/{runbook_id}/answers")
def answer_questions(runbook_id: str, body: AnswersIn, wait: bool = False):
    """Save the engineer's answers. Once every question is answered, the build starts automatically."""
    record = _load_idle(runbook_id)
    for step in (record.get("parsed") or {}).get("steps", []):
        answer = body.answers.get(step["order"])
        if answer and answer.strip():
            step["answer"] = answer.strip()
    remaining = jobs.open_questions(record)
    store.log(record, "Engineer", f"Answered {len(body.answers)} question(s)" + (f", {len(remaining)} still open" if remaining else ""))
    if record["status"] == "needs_answers" and not remaining:
        record["status"] = "parsed"
        store.save(record)
        jobs.start(jobs.build_job, runbook_id, wait=wait)
    return store.get(runbook_id)


class BuildIn(BaseModel):
    feedback: str | None = None


@app.post("/runbooks/{runbook_id}/build")
def build(runbook_id: str, body: BuildIn | None = None, wait: bool = False):
    """Author writes the script, Tester tests and fixes it in the sandbox, Reviewer writes the card.
    Pass feedback to regenerate after a rejection."""
    record = _load_idle(runbook_id)
    if not (record.get("parsed") or {}).get("steps"):
        raise HTTPException(409, "Runbook has not been parsed yet.")
    if jobs.open_questions(record):
        raise HTTPException(409, f"Answer the open questions first (steps {jobs.open_questions(record)}).")
    jobs.start(jobs.build_job, runbook_id, wait=wait, feedback=body.feedback if body else None)
    return store.get(runbook_id)


# Blueprint name for "retry with reviewer feedback".
app.post("/runbooks/{runbook_id}/regenerate")(build)


class DecisionIn(BaseModel):
    reviewer: str
    comment: str | None = None


def required_approvals(record: dict) -> int:
    """Risk tiers from the design doc: high-risk scripts need two engineers."""
    return 2 if (record.get("parsed") or {}).get("risk_tier") == "high" else 1


@app.post("/runbooks/{runbook_id}/approve")
def approve(runbook_id: str, body: DecisionIn):
    record = _load_idle(runbook_id)
    if record["status"] != "awaiting_approval":
        raise HTTPException(409, f"Nothing to approve (status: {record['status']}).")
    reviewer = body.reviewer.strip()
    if not reviewer:
        raise HTTPException(400, "Reviewer name is required.")
    version = record["review"]["script_version"]
    approvals = record.setdefault("approvals", [])
    current = [a for a in approvals if a["script_version"] == version and a["decision"] == "approved"]
    if any(a["reviewer"].lower() == reviewer.lower() for a in current):
        raise HTTPException(409, f"{reviewer} has already approved this version; a second engineer is needed.")

    approvals.append({"reviewer": reviewer, "decision": "approved", "comment": body.comment, "script_version": version, "at": store.now()})
    needed = required_approvals(record)
    if len(current) + 1 >= needed:
        record["status"] = "approved"
        record["approved_version"] = version
        store.log(record, "Engineer", f"{reviewer} approved script v{version} - added to the automation library", "success")
    else:
        store.log(record, "Engineer", f"{reviewer} approved ({len(current) + 1} of {needed}); waiting for a second engineer")
    return store.get(runbook_id)


@app.post("/runbooks/{runbook_id}/reject")
def reject(runbook_id: str, body: DecisionIn, regenerate: bool = True, wait: bool = False):
    """Reject the script. By default the comment goes back to the Author agent as feedback."""
    record = _load_idle(runbook_id)
    if record["status"] not in ("awaiting_approval", "tests_failed"):
        raise HTTPException(409, f"Nothing to reject (status: {record['status']}).")
    if not body.reviewer.strip():
        raise HTTPException(400, "Reviewer name is required.")
    version = record["scripts"][-1]["version"]
    record.setdefault("approvals", []).append(
        {"reviewer": body.reviewer.strip(), "decision": "rejected", "comment": body.comment, "script_version": version, "at": store.now()}
    )
    record["status"] = "rejected"
    store.log(record, "Engineer", f"{body.reviewer.strip()} rejected v{version}: {body.comment or 'no comment'}", "warning")
    if regenerate and body.comment:
        jobs.start(jobs.build_job, runbook_id, wait=wait, feedback=f"Reviewer rejected the script: {body.comment}")
    return store.get(runbook_id)


def _load(runbook_id: str) -> dict:
    record = store.get(runbook_id)
    if not record:
        raise HTTPException(404, "Runbook not found")
    return record


def _load_idle(runbook_id: str) -> dict:
    record = _load(runbook_id)
    if record["status"] in jobs.BUSY_STATUSES:
        raise HTTPException(409, f"Agents are still working on this runbook ({record['status']}).")
    return record
