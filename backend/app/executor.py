"""Runs an approved script on a real server over SSH (called by the worker for "run" jobs).

For an execute run the script is first run in its default dry-run mode; only if that passes is it run
again with --execute. Output is saved as it arrives, so the web app can show it live. The script file
is removed from the server afterwards.
"""
import logging
import secrets
import shlex
import time
from datetime import datetime, timezone

from . import config, ssh, store
from .db import session_scope
from .models import Credential, ScriptRun, Server
from .sandbox import _parse_steps

log = logging.getLogger(__name__)

RUN_TIMEOUT_SECONDS = config.RUN_TIMEOUT_SECONDS
FLUSH_EVERY_SECONDS = 1.0
MAX_OUTPUT_CHARS = 200_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _update(run_id: int, **fields) -> None:
    with session_scope() as s:
        run = s.get(ScriptRun, run_id)
        for key, value in fields.items():
            setattr(run, key, value)


def _append_output(run_id: int, text: str) -> None:
    with session_scope() as s:
        run = s.get(ScriptRun, run_id)
        run.output = ((run.output or "") + text)[-MAX_OUTPUT_CHARS:]


def _cancel_requested(run_id: int) -> bool:
    with session_scope() as s:
        return s.get(ScriptRun, run_id).status == "cancelling"


def _exec(client, command: str, run_id: int, label: str) -> int:
    """Run one command, streaming combined stdout/stderr into the run's output. Returns the exit code."""
    _append_output(run_id, f"\n===== {label}: {command}\n")
    channel = client.get_transport().open_session()
    channel.set_combine_stderr(True)
    channel.settimeout(1.0)
    channel.exec_command(command)
    started = time.monotonic()
    buffer, last_flush = "", time.monotonic()
    while True:
        try:
            chunk = channel.recv(4096)
            if chunk:
                buffer += chunk.decode("utf-8", errors="replace")
            elif channel.exit_status_ready():
                break
        except TimeoutError:
            pass
        except OSError:  # paramiko raises socket.timeout (an OSError subclass) on older Pythons
            pass
        if time.monotonic() - last_flush >= FLUSH_EVERY_SECONDS:
            if buffer:
                _append_output(run_id, buffer)
                buffer = ""
            last_flush = time.monotonic()
            if _cancel_requested(run_id):
                channel.close()
                raise _Cancelled()
        if time.monotonic() - started > RUN_TIMEOUT_SECONDS:
            channel.close()
            raise TimeoutError(f"{label} took longer than {RUN_TIMEOUT_SECONDS}s and was stopped")
        if channel.exit_status_ready() and not channel.recv_ready():
            break
    while channel.recv_ready():
        buffer += channel.recv(4096).decode("utf-8", errors="replace")
    if buffer:
        _append_output(run_id, buffer)
    return channel.recv_exit_status()


class _Cancelled(Exception):
    pass


def execute_run(run_id: int) -> None:
    with session_scope() as s:
        run = s.get(ScriptRun, run_id)
        if run is None or run.status not in ("queued", "cancelling"):
            return
        if run.status == "cancelling":
            run.status, run.finished_at = "cancelled", _now()
            return
        server = s.get(Server, run.server_id) if run.server_id else None
        if server is None:
            run.status, run.error, run.finished_at = "failed", "The server was deleted.", _now()
            return
        credential = s.get(Credential, server.credential_id) if server.credential_id else None
        record_id, version, mode = run.runbook_id, run.script_version, run.mode
        run.status, run.started_at = "running", _now()
        try:
            target = ssh.target_for(server, credential)
        except ssh.SSHError as e:
            run.status, run.error, run.finished_at = "failed", str(e), _now()
            return

    record = store.get(record_id)
    script = next(v["script"] for v in record["scripts"] if v["version"] == version)
    store.log(record_id, "Runner", f"Run #{run_id}: {mode.replace('_', ' ')} on {target.hostname} started")
    started = time.monotonic()
    remote_path = f"/tmp/runbookpilot-{run_id}-{secrets.token_hex(4)}.sh"
    status, error, exit_code, dry_ok = "failed", None, None, None
    client = None
    try:
        client = ssh.connect(target)
        with client.open_sftp() as sftp:
            with sftp.file(remote_path, "w") as f:
                f.write(script.replace("\r\n", "\n"))
            sftp.chmod(remote_path, 0o700)

        exit_code = _exec(client, f"bash {shlex.quote(remote_path)}", run_id, "Dry run")
        dry_ok = exit_code == 0
        if mode == "execute" and dry_ok:
            exit_code = _exec(client, f"bash {shlex.quote(remote_path)} --execute", run_id, "Execute")
        status = "succeeded" if exit_code == 0 else "failed"
        if not dry_ok and mode == "execute":
            error = "The dry run failed, so the script was not executed."
    except _Cancelled:
        status, error = "cancelled", "Cancelled by a user."
    except (ssh.SSHError, TimeoutError) as e:
        error = str(e)
    except Exception as e:  # never leave a run stuck in "running"
        log.exception("Run %s failed", run_id)
        error = f"Unexpected error: {e}"
    finally:
        if client is not None:
            try:
                client.exec_command(f"rm -f {shlex.quote(remote_path)}", timeout=10)
            except Exception:
                pass
            client.close()

    with session_scope() as s:
        run = s.get(ScriptRun, run_id)
        steps = _parse_steps(run.output or "")
        run.status, run.error, run.exit_code, run.dry_run_passed = status, error, exit_code, dry_ok
        run.steps = steps
        run.finished_at = _now()
        run.duration_s = round(time.monotonic() - started, 2)
    level = "success" if status == "succeeded" else "error"
    store.log(record_id, "Runner", f"Run #{run_id} on {target.hostname} {status}" + (f": {error}" if error else ""), level)
