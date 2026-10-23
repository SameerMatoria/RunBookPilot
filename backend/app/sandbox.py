"""Runs a script inside a disposable Docker container and collects per-step results.

Isolation: fresh container per run, removed afterwards, no network, capped CPU/memory/processes,
hard timeout. The script never touches the host or any real server.
"""
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from . import config

IMAGE = "runbookpilot-sandbox:latest"
SANDBOX_DIR = config.PROJECT_DIR / "sandbox"
TIMEOUT_SECONDS = 120
STEP_LINE = re.compile(r"^RBP_STEP\|(\d+)\|(START|OK|SKIP|FAIL)\|(.*)$")

# Docker Desktop's per-user install is not always on PATH for already-open terminals.
_KNOWN_DOCKER = Path.home() / "AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe"


class SandboxError(RuntimeError):
    pass


def docker_bin() -> str:
    found = config.DOCKER_BIN or shutil.which("docker") or (str(_KNOWN_DOCKER) if _KNOWN_DOCKER.exists() else None)
    if not found:
        raise SandboxError("Docker is not installed.")
    return found


def _docker(*args: str, timeout: int = 600, stdin: str | None = None) -> subprocess.CompletedProcess:
    # Binary mode on purpose: text mode on Windows rewrites "\n" as "\r\n", which breaks Bash scripts.
    proc = subprocess.run(
        [docker_bin(), *args],
        input=stdin.replace("\r\n", "\n").encode("utf-8") if stdin is not None else None,
        capture_output=True,
        timeout=timeout,
    )
    proc.stdout = proc.stdout.decode("utf-8", errors="replace")
    proc.stderr = proc.stderr.decode("utf-8", errors="replace")
    return proc


def status() -> dict:
    try:
        proc = _docker("info", "--format", "{{.ServerVersion}}", timeout=20)
    except (SandboxError, subprocess.TimeoutExpired) as e:
        return {"ready": False, "detail": str(e)}
    if proc.returncode != 0:
        return {"ready": False, "detail": "Docker engine is not running. Start Docker Desktop."}
    has_image = _docker("image", "inspect", IMAGE, timeout=20).returncode == 0
    return {"ready": True, "engine": proc.stdout.strip(), "image_built": has_image}


def ensure_image() -> None:
    if _docker("image", "inspect", IMAGE, timeout=20).returncode == 0:
        return
    proc = _docker("build", "-t", IMAGE, str(SANDBOX_DIR), timeout=900)
    if proc.returncode != 0:
        raise SandboxError(f"Sandbox image build failed:\n{proc.stderr[-2000:]}")


def run_script(script: str, execute: bool) -> dict:
    """Run the script in a fresh container. execute=False runs it in its default dry-run mode."""
    ensure_image()
    name = f"rbp-test-{uuid.uuid4().hex[:8]}"
    mode_arg = "--execute" if execute else ""
    # Start nginx like a real server would have it, then run the script from stdin.
    entry = f'nginx; cat > /tmp/runbook.sh; bash /tmp/runbook.sh {mode_arg}'
    started = time.monotonic()
    try:
        proc = _docker(
            "run", "--rm", "-i", "--name", name,
            "--network", "none", "--memory", "256m", "--cpus", "1", "--pids-limit", "256",
            IMAGE, "bash", "-c", entry,
            stdin=script, timeout=TIMEOUT_SECONDS,
        )
        exit_code, stdout, stderr, timed_out = proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as e:
        _docker("rm", "-f", name, timeout=30)
        exit_code, timed_out = -1, True
        stdout = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = f"Timed out after {TIMEOUT_SECONDS}s"

    return {
        "mode": "execute" if execute else "dry_run",
        "exit_code": exit_code,
        "passed": exit_code == 0,
        "timed_out": timed_out,
        "duration_s": round(time.monotonic() - started, 2),
        "steps": _parse_steps(stdout),
        "stdout": stdout[-8000:],
        "stderr": stderr[-4000:],
    }


def _parse_steps(stdout: str) -> list[dict]:
    """Collapse RBP_STEP log lines into one final status per step."""
    steps: dict[int, dict] = {}
    for line in stdout.splitlines():
        m = STEP_LINE.match(line.strip())
        if not m:
            continue
        order, status_, message = int(m.group(1)), m.group(2), m.group(3)
        step = steps.setdefault(order, {"order": order, "status": "START", "messages": []})
        step["messages"].append(message)
        if status_ != "START":
            step["status"] = status_
    # A step that started but never reported OK/SKIP/FAIL crashed mid-way.
    for step in steps.values():
        if step["status"] == "START":
            step["status"] = "FAIL"
    return sorted(steps.values(), key=lambda s: s["order"])
