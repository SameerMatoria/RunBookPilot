"""The test-and-fix loop: retries, the retry cap, and handing over non-script problems."""
from conftest import upload

from app.pipeline import MAX_ATTEMPTS


def test_failed_test_is_fixed_and_retested(client, fakes):
    fakes.sandbox_outcomes = [False]  # first dry run fails, then everything passes
    record = upload(client)
    assert record["status"] == "awaiting_approval"
    assert len(record["scripts"]) == 2
    assert [r["passed"] for r in record["test_runs"]] == [False, True]
    assert record["test_runs"][0]["diagnosis"]["category"] == "script_bug"
    assert record["review"]["attempts"] == 2


def test_retry_cap_hands_over_to_engineer(client, fakes):
    fakes.sandbox_outcomes = [False] * 10
    record = upload(client)
    assert record["status"] == "tests_failed"
    assert len(record["test_runs"]) == MAX_ATTEMPTS + 1
    assert len(record["scripts"]) == MAX_ATTEMPTS + 1
    assert any("Retry limit" in e["message"] for e in record["events"])


def test_environment_problem_is_not_retried(client, fakes):
    fakes.sandbox_outcomes = [False]
    fakes.diagnosis_category = "environment"
    record = upload(client)
    assert record["status"] == "tests_failed"
    assert len(record["test_runs"]) == 1
    assert len(record["scripts"]) == 1


def test_dry_run_then_execute(client, fakes):
    record = upload(client)
    run = record["test_runs"][0]
    assert run["dry_run"]["mode"] == "dry_run"
    assert run["execute"]["mode"] == "execute"
    assert fakes.sandbox_calls == 2
