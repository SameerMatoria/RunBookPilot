"""Reviewer agent: writes the one-minute summary card the approving engineer reads."""
from ..llm import chat_json
from .common import compact_json, compact_script, compact_steps

SYSTEM_PROMPT = """You are the Reviewer agent in RunbookPilot. A runbook was converted into a Bash
script and tested in a disposable sandbox. Write the summary card a busy on-call engineer reads in
one minute before approving it to run on real servers.

Be plain, specific and honest. Use the actual test evidence. Do not oversell: if a branch of the
script was never exercised in the sandbox (e.g. a cleanup that was skipped because the disk was not
full), say so as a risk. Mention anything the engineer must still do by hand.

Return JSON only:
{
  "headline": "one sentence: what the script does",
  "what_it_does": ["short bullet per main action, in order"],
  "changes": ["each change it makes to a server when run with --execute; empty if read-only"],
  "risks": [{"risk": "what could go wrong", "mitigation": "what limits it"}],
  "untested": ["parts of the script the sandbox run did not exercise"],
  "manual_followups": ["things a human must still do"],
  "confidence": "high" | "medium" | "low",
  "confidence_reason": "one sentence",
  "recommendation": "approve" | "approve_with_care" | "reject"
}"""


def review(parsed: dict, script: dict, test_run: dict, attempts: int) -> dict:
    evidence = {
        "passed": test_run.get("passed"),
        "attempts": attempts,
        "dry_run_steps": _step_results(test_run.get("dry_run")),
        "execute_steps": _step_results(test_run.get("execute")),
    }
    prompt = (
        f"Runbook: {parsed.get('title')} (risk tier: {parsed.get('risk_tier')})\n"
        f"Parsed steps: {compact_json(compact_steps(parsed.get('steps', [])))}\n\n"
        f"Script v{script['version']} (comments removed):\n{compact_script(script['script'])}\n\n"
        f"Author notes: {compact_json(script.get('notes', []))}\n\n"
        f"Sandbox evidence: {compact_json(evidence)}"
    )
    return chat_json(SYSTEM_PROMPT, prompt, agent="reviewer")


def _step_results(result: dict | None) -> list[dict] | None:
    """Per-step status plus the last message only (full logs are not needed for the card)."""
    if not result:
        return None
    return [{"order": s["order"], "status": s["status"], "msg": (s.get("messages") or [""])[-1][:160]} for s in result["steps"]]


def _step_results(result: dict | None) -> list[dict] | None:
    """Per-step status plus the last message only (full logs are not needed for the card)."""
    if not result:
        return None
    return [{"order": s["order"], "status": s["status"], "msg": (s.get("messages") or [""])[-1][:160]} for s in result["steps"]]
