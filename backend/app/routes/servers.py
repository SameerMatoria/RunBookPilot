"""Servers and the credentials used to reach them (admins manage; operators can view).

Credential secrets are write-only: the API encrypts them on the way in and never returns them.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import audit, secrets_store, ssh
from ..auth import require
from ..db import session_scope
from ..models import Credential, Server

router = APIRouter(tags=["servers"])


def credential_dict(c: Credential) -> dict:
    return {"id": c.id, "name": c.name, "kind": c.kind, "username": c.username,
            "public_fingerprint": c.public_fingerprint, "has_passphrase": bool(c.encrypted_passphrase),
            "created_at": c.created_at.isoformat() if c.created_at else None}


def server_dict(sv: Server, credentials: dict[int, Credential]) -> dict:
    cred = credentials.get(sv.credential_id) if sv.credential_id else None
    return {
        "id": sv.id, "name": sv.name, "hostname": sv.hostname, "port": sv.port, "os": sv.os,
        "group_name": sv.group_name, "credential_id": sv.credential_id,
        "credential_name": cred.name if cred else None, "username": cred.username if cred else None,
        "host_key_fingerprint": sv.host_key_fingerprint, "verified": bool(sv.host_key), "enabled": sv.enabled,
        "last_check_at": sv.last_check_at.isoformat() if sv.last_check_at else None,
        "last_check_ok": sv.last_check_ok, "last_check_detail": sv.last_check_detail,
    }


def _all_credentials(s) -> dict[int, Credential]:
    return {c.id: c for c in s.scalars(select(Credential))}


# ---------- credentials ----------

@router.get("/credentials")
def list_credentials(user: dict = Depends(require("operator"))):
    with session_scope() as s:
        return [credential_dict(c) for c in s.scalars(select(Credential).order_by(Credential.name))]


class CredentialIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str  # ssh_key | password
    username: str = Field(min_length=1, max_length=128)
    secret: str = Field(min_length=1)
    passphrase: str | None = None


@router.post("/credentials")
def create_credential(body: CredentialIn, request: Request, admin: dict = Depends(require("admin"))):
    if body.kind not in ("ssh_key", "password"):
        raise HTTPException(400, "kind must be ssh_key or password")
    fingerprint = None
    if body.kind == "ssh_key":
        try:
            fingerprint = ssh.fingerprint(ssh.load_private_key(body.secret, body.passphrase))
        except ssh.SSHError as e:
            raise HTTPException(400, str(e))
    try:
        with session_scope() as s:
            cred = Credential(
                name=body.name.strip(), kind=body.kind, username=body.username.strip(),
                encrypted_secret=secrets_store.encrypt(body.secret),
                encrypted_passphrase=secrets_store.encrypt(body.passphrase) if body.passphrase else None,
                public_fingerprint=fingerprint, created_by=admin["id"],
            )
            s.add(cred)
            s.flush()
            result = credential_dict(cred)
    except IntegrityError:
        raise HTTPException(409, f"A credential named {body.name} already exists.")
    audit.record(admin, "server.credential_create", "credential", result["id"], request, name=result["name"], kind=body.kind)
    return result


@router.delete("/credentials/{credential_id}")
def delete_credential(credential_id: int, request: Request, admin: dict = Depends(require("admin"))):
    with session_scope() as s:
        cred = s.get(Credential, credential_id)
        if cred is None:
            raise HTTPException(404, "Credential not found")
        in_use = [sv.name for sv in s.scalars(select(Server).where(Server.credential_id == credential_id))]
        if in_use:
            raise HTTPException(409, f"Still used by: {', '.join(in_use)}")
        name = cred.name
        s.delete(cred)
    audit.record(admin, "server.credential_delete", "credential", credential_id, request, name=name)
    return {"deleted": credential_id}


# ---------- servers ----------

@router.get("/servers")
def list_servers(user: dict = Depends(require("operator"))):
    with session_scope() as s:
        creds = _all_credentials(s)
        return [server_dict(sv, creds) for sv in s.scalars(select(Server).order_by(Server.group_name, Server.name))]


class ServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    hostname: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    os: str = "linux"
    group_name: str | None = None
    credential_id: int | None = None
    enabled: bool = True


@router.post("/servers")
def create_server(body: ServerIn, request: Request, admin: dict = Depends(require("admin"))):
    try:
        with session_scope() as s:
            if body.credential_id and not s.get(Credential, body.credential_id):
                raise HTTPException(400, "Unknown credential")
            sv = Server(**body.model_dump())
            s.add(sv)
            s.flush()
            result = server_dict(sv, _all_credentials(s))
    except IntegrityError:
        raise HTTPException(409, f"A server named {body.name} already exists.")
    audit.record(admin, "server.create", "server", result["id"], request, name=body.name, hostname=body.hostname)
    return result


class ServerUpdate(BaseModel):
    name: str | None = None
    hostname: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    group_name: str | None = None
    credential_id: int | None = None
    enabled: bool | None = None
    reset_host_key: bool = False


@router.patch("/servers/{server_id}")
def update_server(server_id: int, body: ServerUpdate, request: Request, admin: dict = Depends(require("admin"))):
    changes = body.model_dump(exclude_unset=True)
    reset = changes.pop("reset_host_key", False)
    with session_scope() as s:
        sv = s.get(Server, server_id)
        if sv is None:
            raise HTTPException(404, "Server not found")
        for key, value in changes.items():
            setattr(sv, key, value)
        # A new address means a new identity to verify.
        if reset or "hostname" in changes or "port" in changes:
            sv.host_key = sv.host_key_fingerprint = None
        s.flush()
        result = server_dict(sv, _all_credentials(s))
    audit.record(admin, "server.update", "server", server_id, request, **changes, reset_host_key=reset)
    return result


@router.delete("/servers/{server_id}")
def delete_server(server_id: int, request: Request, admin: dict = Depends(require("admin"))):
    with session_scope() as s:
        sv = s.get(Server, server_id)
        if sv is None:
            raise HTTPException(404, "Server not found")
        name = sv.name
        s.delete(sv)
    audit.record(admin, "server.delete", "server", server_id, request, name=name)
    return {"deleted": server_id}


@router.post("/servers/{server_id}/test")
def test_connection(server_id: int, request: Request, admin: dict = Depends(require("admin"))):
    """Connect and run a harmless command. The first successful test pins the server's host key."""
    with session_scope() as s:
        sv = s.get(Server, server_id)
        if sv is None:
            raise HTTPException(404, "Server not found")
        cred = s.get(Credential, sv.credential_id) if sv.credential_id else None
        first_time = not sv.host_key
        try:
            target = ssh.target_for(sv, cred)
        except ssh.SSHError as e:
            raise HTTPException(400, str(e))

    ok, detail, host_key, fp = False, "", None, None
    try:
        client = ssh.connect(target, trust_new_host_key=first_time)
        try:
            host_key, fp = ssh.host_key_of(client)
            _, stdout, _ = client.exec_command("uname -srm; hostname", timeout=10)
            detail = " / ".join(stdout.read().decode(errors="replace").split("\n")).strip(" /")
            ok = True
        finally:
            client.close()
    except ssh.SSHError as e:
        detail = str(e)

    with session_scope() as s:
        sv = s.get(Server, server_id)
        sv.last_check_at, sv.last_check_ok, sv.last_check_detail = datetime.now(timezone.utc), ok, detail
        if ok and first_time:
            sv.host_key, sv.host_key_fingerprint = host_key, fp
        result = server_dict(sv, _all_credentials(s))
    audit.record(admin, "server.test", "server", server_id, request, ok=ok, pinned_host_key=fp if ok and first_time else None)
    return {**result, "pinned_now": ok and first_time}
