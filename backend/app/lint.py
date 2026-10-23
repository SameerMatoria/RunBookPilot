"""Lint gate: static checks every script must pass before it can run, even in the sandbox.

1. Blocked commands: destructive patterns that are never allowed (guardrail from the design doc).
2. ShellCheck: syntax errors and common Bash bugs.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BLOCKED_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*r[a-zA-Z]*\s+(-[a-zA-Z]*\s+)*(/|/\*|~|\$HOME)(\s|$|;)", "Recursive delete of root or home directory"),
    (r"\bmkfs(\.\w+)?\b", "Formatting a filesystem"),
    (r"\bdd\s+.*\bof=/dev/", "Writing raw data to a disk device"),
    (r">\s*/dev/(sd[a-z]|nvme|xvd|hd[a-z])", "Overwriting a disk device"),
    (r"\b(fdisk|parted|wipefs)\b", "Changing disk partitions"),
    (r"\biptables\s+(-F|--flush)\b", "Flushing all firewall rules"),
    (r"\bufw\s+(disable|reset)\b", "Disabling or resetting the firewall"),
    (r"\bchmod\s+(-R\s+)?777\s+/", "Opening permissions on system paths"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "Fork bomb"),
    (r"\b(shutdown|poweroff|halt)\b|\breboot\b(?!-)", "Shutting down or rebooting the server"),
    (r"(password|passwd|secret|api[_-]?key|token)\s*=\s*['\"][^'\"$]{4,}['\"]", "Hard-coded credential"),
]

SHELLCHECK_SEVERITIES = {"error", "warning"}


def _shellcheck_binary() -> str | None:
    local = Path(sys.executable).parent / ("shellcheck.exe" if sys.platform == "win32" else "shellcheck")
    return str(local) if local.exists() else shutil.which("shellcheck")


def check_blocked(script: str) -> list[dict]:
    issues = []
    for lineno, line in enumerate(script.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for pattern, reason in BLOCKED_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append({"line": lineno, "severity": "blocked", "message": reason, "code": line.strip()})
    return issues


def run_shellcheck(script: str) -> list[dict]:
    binary = _shellcheck_binary()
    if not binary:
        return [{"line": 0, "severity": "warning", "message": "ShellCheck not installed; static check skipped", "code": ""}]
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8", newline="\n") as f:
        f.write(script)
        path = f.name
    try:
        proc = subprocess.run([binary, "--format=json", "--shell=bash", path], capture_output=True, text=True, timeout=60)
        findings = json.loads(proc.stdout or "[]")
    finally:
        Path(path).unlink(missing_ok=True)
    return [
        {"line": f["line"], "severity": f["level"], "message": f"SC{f['code']}: {f['message']}", "code": ""}
        for f in findings
        if f["level"] in SHELLCHECK_SEVERITIES
    ]


def lint_script(script: str) -> dict:
    blocked = check_blocked(script)
    shellcheck = run_shellcheck(script)
    errors = [i for i in shellcheck if i["severity"] == "error"]
    return {
        "passed": not blocked and not errors,
        "blocked": blocked,
        "issues": shellcheck,
    }
