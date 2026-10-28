"""Retrying after an error picks up where the run stopped."""
from conftest import upload

from app import jobs


def test_retry_after_review_error_only_redoes_review(client, fakes, monkeypatch):
    calls = {"review": 0}
    real_review = jobs.review

    def flaky_review(*args):
        calls["review"] += 1
        if calls["review"] == 1:
            raise RuntimeError("Request too large for model")
        return real_review(*args)

    monkeypatch.setattr(jobs, "review", flaky_review)
    record = upload(client)
    assert record["status"] == "error"
    assert "too large" in record["error"]
    sandbox_runs_before = fakes.sandbox_calls

    retried = client.post(f"/runbooks/{record['id']}/retry?wait=true").json()
    assert retried["status"] == "awaiting_approval"
    assert retried["error"] is None
    assert len(retried["scripts"]) == 1  # no rewrite
    assert fakes.sandbox_calls == sandbox_runs_before  # no retest
    assert any("retried from the review step" in e["message"] for e in retried["events"])


def test_retry_after_author_error_rebuilds(client, fakes, monkeypatch):
    def broken_author(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(jobs, "write_script", broken_author)
    record = upload(client)
    assert record["status"] == "error"

    monkeypatch.undo()
    from conftest import SAFE_SCRIPT
    monkeypatch.setattr(jobs, "write_script", lambda *a, **k: {"script": SAFE_SCRIPT, "steps": [], "notes": []})
    monkeypatch.setattr(jobs, "review", lambda *a: {"headline": "ok", "recommendation": "approve", "confidence": "high"})
    from app import sandbox
    from conftest import sandbox_result
    monkeypatch.setattr(sandbox, "run_script", lambda script, execute: sandbox_result(execute=execute))
    retried = client.post(f"/runbooks/{record['id']}/retry?wait=true").json()
    assert retried["status"] == "awaiting_approval"
    assert len(retried["scripts"]) == 1


def test_retry_only_when_errored(client, fakes):
    rid = upload(client)["id"]
    assert client.post(f"/runbooks/{rid}/retry").status_code == 409
