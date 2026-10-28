"""Author agent: turns parsed runbook steps into a safe, testable Bash script."""
import json
import re

from ..llm import chat_text
from .common import compact_json, compact_script, compact_steps

SYSTEM_PROMPT = """You are the Author agent in RunbookPilot. You turn parsed IT runbook steps into a
Bash script that an operations team can trust. A Tester agent will run it in a sandbox and a human
engineer will review it, so it must be clear and safe.

Script rules (all mandatory):
1. Start with `#!/usr/bin/env bash` and `set -euo pipefail`.
2. Dry-run by default. A DRY_RUN variable defaults to 1; the script only makes changes when run
   with `--execute`. Every command that changes the system goes through a `run` helper that only
   prints the command in dry-run mode. Read-only checks (status, config tests like `nginx -t`,
   disk usage, health checks) must NOT go through `run`; they always really run, in both modes.
   But a check that verifies the RESULT of a change (a file was created, a config line is now
   present, a user now exists, permissions were changed) cannot pass in dry-run mode because the
   change was not made: in dry-run mode such checks must log SKIP ("would verify ...") instead of
   failing. Likewise, rollback/restore logic only runs when a real change failed, never in dry-run.
3. One function per runbook step, named `step_<order>_<short_name>`, called in order from `main`.
4. Every step function checks its expected result after acting and fails with a clear message if
   the check fails. Add pre-checks before changing anything.
5. Stop on the first failure (exit non-zero) and say which step failed.
6. Print one structured log line per step to stdout, exactly in this format:
   RBP_STEP|<order>|<status>|<message>     where status is START, OK, SKIP or FAIL
7. Idempotent: running it twice does no harm (e.g. only clean up if needed, only restart if needed
   when the runbook allows it).
8. Never hard-code passwords, tokens or keys. If a secret is needed, read it from an environment
   variable and fail if it is missing.
9. Never use destructive commands the runbook does not ask for. Never reboot, format disks,
   flush firewalls or delete outside the paths the runbook names.
10. The script runs ON the target server, so skip "SSH into the server" style steps: implement them
    as a step that logs the hostname and SKIPs, and note it in "notes".
11. Use the engineer's answer when a step has one. If a step is still unclear, implement the safest
    read-only version and explain in "notes".
12. Target servers may lack sudo; use `sudo` only if the runbook does and `$EUID` is not 0.

Reply with exactly two fenced code blocks and nothing else. First the full script:

```bash
#!/usr/bin/env bash
...
```

Then the metadata:

```json
{
  "steps": [{"order": 1, "function": "step_1_name", "summary": "what this function does"}],
  "notes": ["anything the reviewer should know"]
}
```"""

_BASH_BLOCK = re.compile(r"```(?:bash|sh)\s*\n(.*?)\n```", re.DOTALL)
_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def _parse_reply(text: str) -> dict:
    # The script travels as a plain code block, not inside JSON, so the model never has to escape it.
    script = _BASH_BLOCK.search(text)
    if not script or "#!" not in script.group(1):
        raise ValueError("Author agent reply had no bash script block")
    meta = _JSON_BLOCK.search(text)
    metadata = json.loads(meta.group(1)) if meta else {}
    return {
        "language": "bash",
        "script": script.group(1).strip() + "\n",
        "steps": metadata.get("steps", []),
        "notes": metadata.get("notes", []),
    }


def write_script(parsed: dict, feedback: str | None = None, previous_script: str | None = None) -> dict:
    payload = {
        "title": parsed.get("title"),
        "target_os": parsed.get("target_os"),
        "risk_tier": parsed.get("risk_tier"),
        "steps": compact_steps(parsed.get("steps", [])),
    }
    prompt = "Parsed runbook: " + compact_json(payload)
    if feedback:
        prompt += (f"\n\nPrevious script (comments removed to save space):\n```bash\n{compact_script(previous_script)}\n```"
                   f"\n\nFix it based on this feedback:\n{feedback}")
    return chat_text(SYSTEM_PROMPT, prompt, parse=_parse_reply, agent="author")
