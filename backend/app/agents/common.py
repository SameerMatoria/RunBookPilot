"""Helpers that keep agent prompts small (free model tiers cap tokens per request)."""
import json

STEP_FIELDS = ("order", "action", "target", "command", "expected_result", "changes_system", "answer")


def compact_json(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def compact_steps(steps: list[dict]) -> list[dict]:
    """Only the step fields an agent needs, without empty values."""
    return [{k: s[k] for k in STEP_FIELDS if s.get(k) not in (None, "", False)} for s in steps]


def compact_script(script: str) -> str:
    """The script without comment-only lines and blank lines (keeps the shebang)."""
    lines = script.splitlines()
    kept = [l for i, l in enumerate(lines) if l.strip() and not (l.lstrip().startswith("#") and not (i == 0 and l.startswith("#!")))]
    return "\n".join(kept)


def tail(text: str, chars: int) -> str:
    return text if len(text) <= chars else "...\n" + text[-chars:]
