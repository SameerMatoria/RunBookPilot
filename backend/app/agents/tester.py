"""Tester agent: reads a failed sandbox run and explains what went wrong and how to fix it."""
import json

from ..llm import chat_json

SYSTEM_PROMPT = """You are the Tester agent in RunbookPilot. A generated Bash script was run in a
disposable Linux sandbox (Debian, nginx running, no network, runs as root, systemctl is a small
stand-in that supports nginx start/stop/restart/reload/status/is-active). It failed.

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
        "steps": run["steps"],
        "stdout_tail": run["stdout"][-3000:],
        "stderr_tail": run["stderr"][-2000:],
    }
    if lint and not lint.get("passed"):
        evidence["lint"] = lint
    prompt = f"Script:\n{script}\n\nSandbox result:\n{json.dumps(evidence, indent=2)}"
    return chat_json(SYSTEM_PROMPT, prompt)
