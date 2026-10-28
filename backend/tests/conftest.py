"""Test setup: a throwaway database, and fakes for the AI model and the sandbox.

Tests run against SQLite by default. Set TEST_DATABASE_URL to run them against Postgres (CI does).
"""
import os
import tempfile

_db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_db_file}")
# Tests drop every table, so never let them near a real database.
assert "test" in os.environ["DATABASE_URL"].rsplit("/", 1)[-1], "TEST_DATABASE_URL must name a *test* database"
os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, jobs, pipeline, sandbox  # noqa: E402
from app.main import app  # noqa: E402

SAFE_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail
DRY_RUN=1
[[ "${1-}" == "--execute" ]] && DRY_RUN=0
log_step() { echo "RBP_STEP|$1|$2|$3"; }
step_1_check() { log_step 1 START "checking"; log_step 1 OK "fine"; }
step_2_restart() { log_step 2 START "restarting"; log_step 2 OK "restarted"; }
main() { step_1_check; step_2_restart; }
main "$@"
"""


def parsed_runbook(risk="medium", ambiguous_step=None):
    steps = [
        {"order": 1, "action": "Check the service", "target": "web", "command": "systemctl status nginx",
         "expected_result": "active", "changes_system": False, "ambiguous": False, "question": None},
        {"order": 2, "action": "Restart the service", "target": "web", "command": "systemctl restart nginx",
         "expected_result": "restarted", "changes_system": True, "ambiguous": False, "question": None},
    ]
    if ambiguous_step:
        steps[ambiguous_step - 1].update(ambiguous=True, question="Which server?")
    return {"title": "Restart nginx", "target_os": "linux", "risk_tier": risk, "risk_reason": "restarts a service",
            "manual_minutes": 15, "runs_per_month": 30, "steps": steps}


def sandbox_result(passed=True, execute=False, failing_step=None):
    statuses = {1: "OK", 2: "OK"}
    if failing_step:
        statuses[failing_step] = "FAIL"
    return {"mode": "execute" if execute else "dry_run", "exit_code": 0 if passed else 1, "passed": passed,
            "timed_out": False, "duration_s": 0.4,
            "steps": [{"order": o, "status": s, "messages": ["m"]} for o, s in statuses.items()],
            "stdout": "", "stderr": ""}


class Fakes:
    """Controls what the fake agents and sandbox return in a test."""

    def __init__(self):
        self.parsed = parsed_runbook()
        self.sandbox_outcomes = []  # list of bools, one per sandbox run; default: always pass
        self.diagnosis_category = "script_bug"
        self.author_calls = []
        self.sandbox_calls = 0


@pytest.fixture(autouse=True)
def fresh_db():
    db.Base.metadata.drop_all(db.engine)
    db.create_all()
    yield


@pytest.fixture
def fakes(monkeypatch):
    f = Fakes()

    def fake_write_script(parsed, feedback=None, previous_script=None):
        f.author_calls.append(feedback)
        return {"language": "bash", "script": SAFE_SCRIPT, "steps": [], "notes": ["fake"]}

    def fake_run_script(script, execute):
        f.sandbox_calls += 1
        passed = f.sandbox_outcomes.pop(0) if f.sandbox_outcomes else True
        return sandbox_result(passed=passed, execute=execute, failing_step=None if passed else 2)

    monkeypatch.setattr(jobs, "parse_runbook", lambda text: f.parsed)
    monkeypatch.setattr(jobs, "write_script", fake_write_script)
    monkeypatch.setattr(pipeline, "write_script", fake_write_script)
    monkeypatch.setattr(pipeline, "diagnose", lambda script, run, lint=None: {
        "failed_step": 2, "category": f.diagnosis_category, "diagnosis": "step 2 broke", "fix": "fix step 2"})
    monkeypatch.setattr(jobs, "review", lambda parsed, script, run, attempts: {
        "headline": "Restarts nginx", "recommendation": "approve", "confidence": "high", "risks": []})
    monkeypatch.setattr(sandbox, "run_script", fake_run_script)
    return f


PASSWORD = "correct-horse-battery"
TEST_USERS = {
    "alice": ("submitter",),          # uploads runbooks
    "bob": ("approver",),             # reviews them
    "carol": ("approver", "operator"),
    "root": ("admin",),
}


@pytest.fixture
def users(fresh_db):
    from app import auth

    return {name: auth.create_local_user(name, PASSWORD, name.title(), roles) for name, roles in TEST_USERS.items()}


@pytest.fixture
def client_as(users):
    """Factory: a TestClient signed in as the given test user."""

    def make(username):
        c = TestClient(app)
        response = c.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return c

    return make


@pytest.fixture
def client(client_as):
    """Signed in as alice, a submitter."""
    return client_as("alice")


def upload(client, name="runbook.md", text="1. Restart nginx", wait=True):
    response = client.post(f"/runbooks?wait={str(wait).lower()}", files={"file": (name, text.encode())})
    assert response.status_code == 200, response.text
    return response.json()
