"""Phase 3: credentials, servers, running approved scripts over SSH, schedules and alert webhooks.
SSH is faked; a real end-to-end run against the demo server is done by hand (see README)."""
from datetime import datetime, timedelta, timezone

import pytest

from app import runs as runs_module
from app import ssh
from app.db import session_scope
from app.models import Credential, Schedule
from app.worker import Worker
from conftest import parsed_runbook, upload

GOOD_OUTPUT = "RBP_STEP|1|START|checking\nRBP_STEP|1|OK|fine\nRBP_STEP|2|START|restart\nRBP_STEP|2|OK|done\n"


class FakeChannel:
    def __init__(self, fake, command):
        self.fake, self.command = fake, command
        dry = "--execute" not in command
        self.data = (fake.dry_output if dry else fake.exec_output).encode()
        self.code = fake.dry_code if dry else fake.exec_code
        fake.commands.append(command)

    def set_combine_stderr(self, _): pass
    def settimeout(self, _): pass
    def exec_command(self, _): pass
    def recv_ready(self): return bool(self.data)
    def exit_status_ready(self): return not self.data
    def recv_exit_status(self): return self.code
    def close(self): pass

    def recv(self, n):
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk


class FakeSFTP:
    def __init__(self, fake): self.fake = fake
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def chmod(self, path, mode): self.fake.chmods.append((path, mode))

    def file(self, path, mode):
        fake = self.fake

        class F:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def write(self, text): fake.uploaded[path] = text
        return F()


class FakeSSH:
    """Stands in for a server: records commands; outputs and exit codes are configurable."""

    def __init__(self):
        self.dry_output, self.dry_code = GOOD_OUTPUT, 0
        self.exec_output, self.exec_code = GOOD_OUTPUT, 0
        self.commands, self.uploaded, self.chmods = [], {}, []
        self.connects = []
        self.host_key = ("ssh-ed25519 AAAAfake", "SHA256:fakefingerprint")

    def connect(self, target, trust_new_host_key=False):
        if not target.host_key and not trust_new_host_key:
            raise ssh.SSHError("This server's identity hasn't been verified yet.")
        self.connects.append((target, trust_new_host_key))
        return FakeClient(self)


class SessionChannel(FakeChannel):
    """A channel whose command is only known when exec_command is called (like paramiko's)."""

    def __init__(self, fake):
        self.fake = fake

    def exec_command(self, command):
        FakeChannel.__init__(self, self.fake, command)


class FakeClient:
    def __init__(self, fake):
        self.fake = fake

    def get_transport(self):
        fake = self.fake
        return type("Transport", (), {"open_session": lambda _self: SessionChannel(fake)})()

    def open_sftp(self):
        return FakeSFTP(self.fake)

    def exec_command(self, command, timeout=None):
        self.fake.commands.append(command)
        out = type("Out", (), {"read": lambda _self: b"Linux 6.1 x86_64\ndemo-server\n"})()
        return None, out, None

    def close(self):
        pass


@pytest.fixture
def fake_ssh(monkeypatch):
    fake = FakeSSH()
    monkeypatch.setattr(ssh, "connect", fake.connect)
    monkeypatch.setattr(ssh, "host_key_of", lambda client: fake.host_key)
    return fake


@pytest.fixture
def approved(client, client_as, fakes):
    rid = upload(client)["id"]
    assert client_as("bob").post(f"/runbooks/{rid}/approve").json()["status"] == "approved"
    return rid


@pytest.fixture
def server(client_as, fake_ssh):
    root = client_as("root")
    cred = root.post("/credentials", json={"name": "ops", "kind": "password", "username": "ops", "secret": "pa55word!"}).json()
    sv = root.post("/servers", json={"name": "web-01", "hostname": "10.0.0.5", "credential_id": cred["id"], "group_name": "Contoso"}).json()
    tested = root.post(f"/servers/{sv['id']}/test").json()
    assert tested["last_check_ok"] and tested["pinned_now"] and tested["verified"]
    return tested


def run_worker_until_idle():
    w = Worker()
    while w.run_one():
        pass


# ---------- credentials and servers ----------

def test_credential_secret_is_encrypted_and_never_returned(client_as, users):
    root = client_as("root")
    cred = root.post("/credentials", json={"name": "db", "kind": "password", "username": "dba", "secret": "TopSecret123"}).json()
    assert "secret" not in cred and "encrypted_secret" not in cred
    assert "TopSecret123" not in str(root.get("/credentials").json())
    with session_scope() as s:
        assert "TopSecret123" not in s.get(Credential, cred["id"]).encrypted_secret


def test_invalid_private_key_rejected(client_as, users):
    r = client_as("root").post("/credentials", json={"name": "k", "kind": "ssh_key", "username": "u", "secret": "not a key"})
    assert r.status_code == 400


def test_only_admins_manage_servers_operators_can_view(client_as, server):
    carol = client_as("carol")  # approver + operator
    assert carol.get("/servers").status_code == 200
    assert carol.post("/servers", json={"name": "x", "hostname": "h"}).status_code == 403
    assert client_as("alice").get("/servers").status_code == 403


def test_first_test_pins_host_key_later_tests_dont_repin(client_as, server, fake_ssh):
    assert server["host_key_fingerprint"] == "SHA256:fakefingerprint"
    again = client_as("root").post(f"/servers/{server['id']}/test").json()
    assert again["pinned_now"] is False
    assert fake_ssh.connects[-1][1] is False  # second connection did not trust a new key


def test_changing_hostname_requires_reverification(client_as, server):
    updated = client_as("root").patch(f"/servers/{server['id']}", json={"hostname": "10.0.0.99"}).json()
    assert updated["verified"] is False


# ---------- running approved scripts ----------

def test_operator_runs_approved_script_dry_run_then_execute(client_as, approved, server, fake_ssh):
    carol = client_as("carol")
    created = carol.post(f"/runbooks/{approved}/runs", json={"server_ids": [server["id"]], "mode": "execute"}).json()
    assert created[0]["status"] == "queued"
    run_worker_until_idle()

    run = carol.get(f"/runs/{created[0]['id']}").json()
    assert run["status"] == "succeeded", run
    assert run["dry_run_passed"] is True
    assert [s["status"] for s in run["steps"]] == ["OK", "OK"]
    assert any(c.startswith("bash /tmp/runbookpilot-") and c.endswith("--execute") for c in fake_ssh.commands)
    assert any(c.startswith("rm -f /tmp/runbookpilot-") for c in fake_ssh.commands)  # cleaned up
    assert list(fake_ssh.chmods)[0][1] == 0o700
    assert run["script_sha256"] and len(run["script_sha256"]) == 64


def test_failed_dry_run_stops_execute(client_as, approved, server, fake_ssh):
    fake_ssh.dry_output, fake_ssh.dry_code = "RBP_STEP|1|START|x\nRBP_STEP|1|FAIL|nginx config broken\n", 1
    carol = client_as("carol")
    rid = carol.post(f"/runbooks/{approved}/runs", json={"server_ids": [server["id"]], "mode": "execute"}).json()[0]["id"]
    run_worker_until_idle()
    run = carol.get(f"/runs/{rid}").json()
    assert run["status"] == "failed"
    assert "dry run failed" in run["error"]
    assert not any(c.endswith("--execute") for c in fake_ssh.commands)


def test_only_operators_can_run(client_as, approved, server):
    assert client_as("bob").post(f"/runbooks/{approved}/runs", json={"server_ids": [server["id"]]}).status_code == 403


def test_unapproved_runbook_cannot_run(client, client_as, fakes, server):
    rid = upload(client)["id"]  # awaiting approval
    r = client_as("carol").post(f"/runbooks/{rid}/runs", json={"server_ids": [server["id"]], "mode": "dry_run"})
    assert r.status_code == 409


def test_unverified_server_cannot_run(client_as, approved, fake_ssh):
    root = client_as("root")
    cred = root.post("/credentials", json={"name": "c2", "kind": "password", "username": "u", "secret": "x"}).json()
    sv = root.post("/servers", json={"name": "new-box", "hostname": "h", "credential_id": cred["id"]}).json()
    r = client_as("carol").post(f"/runbooks/{approved}/runs", json={"server_ids": [sv["id"]], "mode": "dry_run"})
    assert r.status_code == 400 and "verified" in r.json()["detail"]


def test_high_risk_execute_needs_ticket(client, client_as, fakes, server):
    fakes.parsed = parsed_runbook(risk="high")
    rid = upload(client)["id"]
    client_as("bob").post(f"/runbooks/{rid}/approve")
    client_as("root").post(f"/runbooks/{rid}/approve")
    carol = client_as("carol")
    assert carol.post(f"/runbooks/{rid}/runs", json={"server_ids": [server["id"]], "mode": "execute"}).status_code == 400
    ok = carol.post(f"/runbooks/{rid}/runs", json={"server_ids": [server["id"]], "mode": "execute", "ticket": "CHG-1042"})
    assert ok.status_code == 200 and ok.json()[0]["ticket"] == "CHG-1042"


def test_cancel_queued_run(client_as, approved, server, fake_ssh):
    carol = client_as("carol")
    rid = carol.post(f"/runbooks/{approved}/runs", json={"server_ids": [server["id"]]}).json()[0]["id"]
    assert carol.post(f"/runs/{rid}/cancel").json()["status"] == "cancelling"
    run_worker_until_idle()
    assert carol.get(f"/runs/{rid}").json()["status"] == "cancelled"
    assert fake_ssh.commands == ["uname -srm; hostname"]  # only the earlier connection test ran


def test_measured_metrics(client_as, approved, server, fake_ssh):
    carol = client_as("carol")
    carol.post(f"/runbooks/{approved}/runs", json={"server_ids": [server["id"]], "mode": "execute"})
    run_worker_until_idle()
    m = carol.get("/metrics").json()["measured"]
    assert m["execute_runs"] == 1 and m["succeeded"] == 1 and m["success_rate"] == 100
    assert m["hours_saved"] == pytest.approx(0.2, abs=0.05)  # 15 manual minutes, a fraction of a second scripted


# ---------- schedules ----------

def test_schedule_starts_runs_when_due(client_as, approved, server, fake_ssh):
    carol = client_as("carol")
    sched = carol.post(f"/runbooks/{approved}/schedules",
                       json={"name": "nightly", "cron": "0 2 * * *", "server_ids": [server["id"]], "mode": "execute"}).json()
    assert sched["next_run_at"]
    assert carol.post(f"/runbooks/{approved}/schedules", json={"name": "bad", "cron": "every day", "server_ids": [server["id"]]}).status_code == 400

    assert runs_module.run_due_schedules() == 0  # not due yet
    with session_scope() as s:
        s.get(Schedule, sched["id"]).next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert runs_module.run_due_schedules() == 1
    run_worker_until_idle()
    history = carol.get(f"/runs?runbook_id={approved}").json()
    assert history[0]["trigger"] == "schedule" and history[0]["status"] == "succeeded"


# ---------- alert webhooks ----------

def test_alert_webhook(client, client_as, approved, server, fake_ssh):
    from fastapi.testclient import TestClient

    from app.main import app

    carol = client_as("carol")
    trig = carol.post(f"/runbooks/{approved}/triggers", json={"name": "disk alert", "server_ids": [server["id"]], "cooldown_minutes": 5}).json()
    token = trig["token"]
    assert "token" not in carol.get(f"/runbooks/{approved}/triggers").json()[0]  # shown once only

    monitor = TestClient(app)  # no user session: authenticated by the trigger token
    assert monitor.post(trig["url_path"], headers={"X-RunbookPilot-Token": "wrong"}).status_code == 401
    started = monitor.post(trig["url_path"], headers={"X-RunbookPilot-Token": token}, json={"host": "web-01"}).json()
    assert len(started["started"]) == 1
    again = monitor.post(trig["url_path"], headers={"X-RunbookPilot-Token": token}).json()
    assert again["started"] == [] and "cooling down" in again["skipped"]

    run_worker_until_idle()
    run = carol.get(f"/runs/{started['started'][0]}").json()
    assert run["trigger"] == "alert" and run["requested_by_name"] == "Alert trigger"


def test_high_risk_cannot_auto_execute_from_alerts(client, client_as, fakes, server):
    fakes.parsed = parsed_runbook(risk="high")
    rid = upload(client)["id"]
    client_as("bob").post(f"/runbooks/{rid}/approve")
    client_as("root").post(f"/runbooks/{rid}/approve")
    r = client_as("carol").post(f"/runbooks/{rid}/triggers", json={"name": "t", "server_ids": [server["id"]], "mode": "execute"})
    assert r.status_code == 400


def test_runs_are_audited(client_as, approved, server, fake_ssh):
    client_as("carol").post(f"/runbooks/{approved}/runs", json={"server_ids": [server["id"]]})
    actions = [a["action"] for a in client_as("root").get("/audit").json()]
    for expected in ["run.start", "server.test", "server.create", "server.credential_create"]:
        assert expected in actions
