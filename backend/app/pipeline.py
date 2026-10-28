"""Test-and-fix loop: lint, dry-run and execute the script in the sandbox; on failure the Tester
agent diagnoses it and the Author agent fixes it. At most MAX_ATTEMPTS fix rounds."""
from . import sandbox, store
from .agents.author import write_script
from .agents.tester import diagnose
from .lint import lint_script

MAX_ATTEMPTS = 3


def new_script_version(runbook_id: str, authored: dict, feedback: str | None, author: str) -> dict:
    return store.add_script(runbook_id, author=author, feedback=feedback, authored=authored, lint=lint_script(authored["script"]))


def _badges(result: dict) -> str:
    return " ".join(f"{s['order']}:{s['status']}" for s in result["steps"]) or "no steps reported"


def _test_once(runbook_id: str, script: dict, attempt: int) -> dict:
    """Lint gate first, then dry-run, then execute. Stops at the first stage that fails."""
    lint = script["lint"]
    result = {"attempt": attempt, "script_version": script["version"], "lint_passed": lint["passed"],
              "dry_run": None, "execute": None}
    if not lint["passed"]:
        store.log(runbook_id, "Lint", f"v{script['version']} blocked: {len(lint['blocked'])} blocked command(s), "
                  f"{sum(i['severity'] == 'error' for i in lint['issues'])} error(s)", "error")
        return {**result, "passed": False, "failed_stage": "lint"}
    store.log(runbook_id, "Lint", f"v{script['version']} passed static checks")

    store.log(runbook_id, "Sandbox", f"Attempt {attempt}: dry run in a fresh container")
    result["dry_run"] = sandbox.run_script(script["script"], execute=False)
    ok = result["dry_run"]["passed"]
    store.log(runbook_id, "Sandbox", f"Dry run {'passed' if ok else 'FAILED'} - {_badges(result['dry_run'])}",
              "success" if ok else "error")
    if not ok:
        return {**result, "passed": False, "failed_stage": "dry_run"}

    store.log(runbook_id, "Sandbox", f"Attempt {attempt}: real run (--execute) in a fresh container")
    result["execute"] = sandbox.run_script(script["script"], execute=True)
    ok = result["execute"]["passed"]
    store.log(runbook_id, "Sandbox", f"Execute {'passed' if ok else 'FAILED'} - {_badges(result['execute'])}",
              "success" if ok else "error")
    return {**result, "passed": ok, "failed_stage": None if ok else "execute"}


def test_and_fix(runbook_id: str, parsed: dict) -> dict:
    """Test the latest script; on failure diagnose, fix and retest. Returns a summary."""
    for attempt in range(1, MAX_ATTEMPTS + 2):  # first test + up to MAX_ATTEMPTS fixes
        current = store.latest_script(runbook_id)
        run = _test_once(runbook_id, current, attempt)
        run_id = store.add_test_run(runbook_id, run)

        if run["passed"]:
            return {"passed": True, "attempts": attempt, "script_version": current["version"], "run": run}

        failed = run.get(run["failed_stage"]) if run["failed_stage"] != "lint" else None
        store.log(runbook_id, "Tester", "Reading the failure logs")
        diagnosis = diagnose(current["script"], failed or _lint_as_run(current["lint"]), current["lint"])
        store.set_diagnosis(run_id, diagnosis)
        run["diagnosis"] = diagnosis
        store.log(runbook_id, "Tester", f"[{diagnosis.get('category')}] step {diagnosis.get('failed_step')}: {diagnosis.get('diagnosis')}", "warning")

        if diagnosis.get("category") != "script_bug":
            store.log(runbook_id, "Tester", "Not a script bug - handing over to the engineer", "error")
            break
        if attempt > MAX_ATTEMPTS:
            store.log(runbook_id, "Tester", f"Retry limit ({MAX_ATTEMPTS} fixes) reached - handing over to the engineer", "error")
            break

        feedback = f"Sandbox test failed at step {diagnosis.get('failed_step')}: {diagnosis.get('diagnosis')}\nFix: {diagnosis.get('fix')}"
        store.log(runbook_id, "Author", f"Fixing the script (fix {attempt} of {MAX_ATTEMPTS})")
        authored = write_script(parsed, feedback=feedback, previous_script=current["script"])
        version = new_script_version(runbook_id, authored, feedback, author="tester_loop")
        store.log(runbook_id, "Author", f"Wrote script v{version['version']}")

    return {"passed": False, "attempts": attempt, "script_version": store.latest_script(runbook_id)["version"], "run": run}


def _lint_as_run(lint: dict) -> dict:
    lines = [f"line {i['line']}: {i['message']}" for i in lint["blocked"] + lint["issues"]]
    return {"mode": "lint", "exit_code": 1, "timed_out": False, "steps": [], "stdout": "", "stderr": "\n".join(lines)}
