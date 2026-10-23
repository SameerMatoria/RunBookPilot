"""Test-and-fix loop: lint, dry-run and execute the script in the sandbox; on failure the Tester
agent diagnoses it and the Author agent fixes it. At most MAX_ATTEMPTS fix rounds."""
from . import sandbox, store
from .agents.author import write_script
from .agents.tester import diagnose
from .lint import lint_script

MAX_ATTEMPTS = 3


def new_script_version(record: dict, authored: dict, feedback: str | None, author: str) -> dict:
    scripts = record.setdefault("scripts", [])
    version = {
        "version": len(scripts) + 1,
        "created_at": store.now(),
        "feedback": feedback,
        "author": author,
        **authored,
        "lint": lint_script(authored["script"]),
    }
    scripts.append(version)
    return version


def _badges(result: dict) -> str:
    return " ".join(f"{s['order']}:{s['status']}" for s in result["steps"]) or "no steps reported"


def _test_once(record: dict, script: dict, attempt: int) -> dict:
    """Lint gate first, then dry-run, then execute. Stops at the first stage that fails."""
    lint = script["lint"]
    result = {"attempt": attempt, "script_version": script["version"], "started_at": store.now(),
              "lint_passed": lint["passed"], "dry_run": None, "execute": None}
    if not lint["passed"]:
        store.log(record, "Lint", f"v{script['version']} blocked: {len(lint['blocked'])} blocked command(s), "
                  f"{sum(i['severity'] == 'error' for i in lint['issues'])} error(s)", "error")
        return {**result, "passed": False, "failed_stage": "lint"}
    store.log(record, "Lint", f"v{script['version']} passed static checks")

    store.log(record, "Sandbox", f"Attempt {attempt}: dry run in a fresh container")
    result["dry_run"] = sandbox.run_script(script["script"], execute=False)
    store.log(record, "Sandbox", f"Dry run {'passed' if result['dry_run']['passed'] else 'FAILED'} - {_badges(result['dry_run'])}",
              "success" if result["dry_run"]["passed"] else "error")
    if not result["dry_run"]["passed"]:
        return {**result, "passed": False, "failed_stage": "dry_run"}

    store.log(record, "Sandbox", f"Attempt {attempt}: real run (--execute) in a fresh container")
    result["execute"] = sandbox.run_script(script["script"], execute=True)
    passed = result["execute"]["passed"]
    store.log(record, "Sandbox", f"Execute {'passed' if passed else 'FAILED'} - {_badges(result['execute'])}",
              "success" if passed else "error")
    return {**result, "passed": passed, "failed_stage": None if passed else "execute"}


def test_and_fix(record: dict) -> dict:
    """Mutates and saves record: appends test runs and any fixed script versions. Returns a summary."""
    test_runs = record.setdefault("test_runs", [])

    for attempt in range(1, MAX_ATTEMPTS + 2):  # first test + up to MAX_ATTEMPTS fixes
        current = record["scripts"][-1]
        run = _test_once(record, current, attempt)
        test_runs.append(run)
        store.save(record)

        if run["passed"]:
            return {"passed": True, "attempts": attempt, "script_version": current["version"], "run": run}

        failed = run.get(run["failed_stage"]) if run["failed_stage"] != "lint" else None
        store.log(record, "Tester", "Reading the failure logs")
        diagnosis = diagnose(current["script"], failed or _lint_as_run(current["lint"]), current["lint"])
        run["diagnosis"] = diagnosis
        store.log(record, "Tester", f"[{diagnosis.get('category')}] step {diagnosis.get('failed_step')}: {diagnosis.get('diagnosis')}", "warning")

        if diagnosis.get("category") != "script_bug":
            store.log(record, "Tester", "Not a script bug - handing over to the engineer", "error")
            break
        if attempt > MAX_ATTEMPTS:
            store.log(record, "Tester", f"Retry limit ({MAX_ATTEMPTS} fixes) reached - handing over to the engineer", "error")
            break

        feedback = f"Sandbox test failed at step {diagnosis.get('failed_step')}: {diagnosis.get('diagnosis')}\nFix: {diagnosis.get('fix')}"
        store.log(record, "Author", f"Fixing the script (fix {attempt} of {MAX_ATTEMPTS})")
        authored = write_script(record["parsed"], feedback=feedback, previous_script=current["script"])
        new_script_version(record, authored, feedback, author="tester_loop")
        store.log(record, "Author", f"Wrote script v{record['scripts'][-1]['version']}")

    return {"passed": False, "attempts": attempt, "script_version": record["scripts"][-1]["version"], "run": test_runs[-1]}


def _lint_as_run(lint: dict) -> dict:
    lines = [f"line {i['line']}: {i['message']}" for i in lint["blocked"] + lint["issues"]]
    return {"mode": "lint", "exit_code": 1, "timed_out": False, "steps": [], "stdout": "", "stderr": "\n".join(lines)}
