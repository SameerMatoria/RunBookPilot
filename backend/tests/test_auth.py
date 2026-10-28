"""Sign-in, roles, separation of duties, user management, Entra tokens and the audit log."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import auth, config
from app.main import app
from conftest import PASSWORD, upload


def test_everything_needs_sign_in(users):
    anon = TestClient(app)
    assert anon.get("/health").status_code == 200
    for path in ["/runbooks", "/metrics", "/sandbox", "/auth/me"]:
        assert anon.get(path).status_code == 401, path


def test_login_logout_and_bad_password(users):
    c = TestClient(app)
    assert c.post("/auth/login", json={"username": "alice", "password": "nope-nope"}).status_code == 401
    ok = c.post("/auth/login", json={"username": "ALICE", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["user"]["roles"] == ["submitter"]
    assert c.get("/auth/me").json()["username"] == "alice"
    c.post("/auth/logout")
    assert c.get("/auth/me").status_code == 401


def test_bearer_token_works_for_scripts(users):
    token = TestClient(app).post("/auth/login", json={"username": "bob", "password": PASSWORD}).json()["token"]
    assert TestClient(app).get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["username"] == "bob"


def test_roles_are_enforced(client, client_as, fakes):
    rid = upload(client)["id"]
    assert client.post(f"/runbooks/{rid}/approve").status_code == 403          # submitter can't approve
    assert client_as("bob").post("/runbooks", files={"file": ("a.md", b"x")}).status_code == 403  # approver can't upload
    assert client.get("/users").status_code == 403                              # only admins manage users
    assert client.get("/audit").status_code == 403


def test_nobody_approves_their_own_runbook(client_as, fakes):
    root = client_as("root")  # admins can upload and approve, but not their own submission
    rid = upload(root)["id"]
    response = root.post(f"/runbooks/{rid}/approve")
    assert response.status_code == 403
    assert "someone else" in response.json()["detail"]


def test_disabled_user_is_locked_out(client_as, users):
    alice = client_as("alice")
    root = client_as("root")
    assert root.patch(f"/users/{users['alice']['id']}", json={"active": False}).status_code == 200
    assert alice.get("/auth/me").status_code == 401
    assert TestClient(app).post("/auth/login", json={"username": "alice", "password": PASSWORD}).status_code == 401


def test_admin_manages_users(client_as, users):
    root = client_as("root")
    created = root.post("/users", json={"username": "dev1", "password": "longenough1", "roles": ["approver"]}).json()
    assert created["roles"] == ["approver"]
    assert root.post("/users", json={"username": "x", "password": "short", "roles": []}).status_code == 400
    assert root.post("/users", json={"username": "y", "password": "longenough1", "roles": ["god"]}).status_code == 400
    updated = root.patch(f"/users/{created['id']}", json={"roles": ["approver", "operator"]}).json()
    assert updated["roles"] == ["approver", "operator"]
    # an admin can't lock themselves out
    assert root.patch(f"/users/{users['root']['id']}", json={"roles": ["submitter"]}).status_code == 400


def test_first_admin_setup_only_when_empty(fresh_db):
    c = TestClient(app)
    assert c.get("/auth/config").json()["needs_setup"] is True
    made = c.post("/auth/setup", json={"username": "owner", "password": "longenough1"})
    assert made.status_code == 200 and made.json()["user"]["roles"] == ["admin"]
    assert TestClient(app).post("/auth/setup", json={"username": "evil", "password": "longenough1"}).status_code == 409


def test_passwords_are_hashed():
    stored = auth.hash_password("s3cret-pass")
    assert "s3cret" not in stored
    assert auth.verify_password("s3cret-pass", stored)
    assert not auth.verify_password("wrong", stored)


def test_audit_log_records_actions(client, client_as, fakes):
    TestClient(app).post("/auth/login", json={"username": "alice", "password": "bad-password"})
    rid = upload(client)["id"]
    client_as("bob").post(f"/runbooks/{rid}/approve")
    actions = [a["action"] for a in client_as("root").get("/audit").json()]
    for expected in ["auth.login_failed", "runbook.upload", "runbook.approve", "auth.login"]:
        assert expected in actions


# ---------- Microsoft Entra ID ----------

@pytest.fixture
def entra(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(config, "ENTRA_TENANT_ID", "tenant-1")
    monkeypatch.setattr(config, "ENTRA_CLIENT_ID", "client-1")
    real_verify = auth.verify_entra_token
    monkeypatch.setattr(auth, "verify_entra_token", lambda token: real_verify(token, signing_key=key.public_key()))

    def token(**overrides):
        now = datetime.now(timezone.utc)
        claims = {"iss": "https://login.microsoftonline.com/tenant-1/v2.0", "aud": "client-1", "oid": "oid-123",
                  "preferred_username": "dana@contoso.com", "name": "Dana", "iat": now, "exp": now + timedelta(hours=1)}
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256")

    return token


def test_entra_sign_in_creates_user_with_default_role(fresh_db, entra):
    c = TestClient(app)
    response = c.post("/auth/entra", json={"id_token": entra()})
    assert response.status_code == 200
    assert response.json()["user"]["roles"] == ["submitter"]
    assert c.get("/auth/me").json()["auth_provider"] == "entra"


def test_entra_app_roles_are_synced(fresh_db, entra):
    c = TestClient(app)
    assert c.post("/auth/entra", json={"id_token": entra(roles=["Approver", "Operator"])}).json()["user"]["roles"] == ["approver", "operator"]


def test_entra_rejects_wrong_audience_or_expired(fresh_db, entra):
    c = TestClient(app)
    assert c.post("/auth/entra", json={"id_token": entra(aud="someone-else")}).status_code == 401
    expired = datetime.now(timezone.utc) - timedelta(hours=2)
    assert c.post("/auth/entra", json={"id_token": entra(exp=expired)}).status_code == 401
