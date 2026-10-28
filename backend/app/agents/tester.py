"""Tester agent: reads a failed sandbox run and explains what went wrong and how to fix it."""
from ..llm import chat_json
from .common import compact_json, tail

SYSTEM_PROMPT = """You are the Tester agent in RunbookPilot. A generated Bash script was run in a
disposable Linux sandbox. It failed. The sandbox is Debian 12, runs as root, has no network, and has
two services running: nginx (port 80, /health) and myapp (port 8080, /health). systemctl is a small
stand-in that supports start/stop/restart/reload/status/is-active for those two services only; it
has no journalctl. Tools available: coreutils, findutils, gawk, curl, openssl, iproute2 (ss), procps,
tar, gzip, sudo, useradd/groupadd.

Read the script, the per-step results and the logs, then decide:
- "script_bug": the script itself is wrong (bad syntax, wrong check, wrong command, bad quoting).
- "environment": the script is fine but the sandbox cannot support it (e.g. needs a service or
  network the sandbox does not have). Do not ask for the script to be weakened in this case.
- "runbook_issue": the runbook's own instructions cannot work as written.

Never suggest removing a safety check, skipping a step, or faking a result to make the test pass.

Return JSON only:
{
  "failed_step": <step order number, or null>,
  "category": "script_bug" | "environment" | "runbook_issue",
  "diagnosis": "one or two sentences, plain language",
  "fix": "specific instruction for the Author agent, or null if category is not script_bug"
}"""


def diagnose(script: str, run: dict, lint: dict | None = None) -> dict:
    evidence = {
        "mode": run["mode"],
        "exit_code": run["exit_code"],
        "timed_out": run["timed_out"],
        "steps": [{"order": s["order"], "status": s["status"], "msg": (s.get("messages") or [""])[-1][:200]} for s in run["steps"]],
        "stdout_tail": tail(run["stdout"], 2000),
        "stderr_tail": tail(run["stderr"], 1500),
    }
    if lint and not lint.get("passed"):
        evidence["lint"] = lint
    # The full script is kept (not compacted) because error messages refer to its line numbers.
    prompt = f"Script:\n{script}\n\nSandbox result: {compact_json(evidence)}"
    return chat_json(SYSTEM_PROMPT, prompt, agent="tester")
