"""Database tables."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# JSONB on Postgres, plain JSON elsewhere (SQLite in tests).
Json = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Runbook(Base):
    __tablename__ = "runbooks"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    source_file: Mapped[str] = mapped_column(String(255))
    source_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[dict | None] = mapped_column(Json)
    review: Mapped[dict | None] = mapped_column(Json)
    approved_version: Mapped[int | None] = mapped_column(Integer)
    submitted_by: Mapped[str | None] = mapped_column(String(255))

    scripts: Mapped[list["ScriptVersion"]] = relationship(
        back_populates="runbook", order_by="ScriptVersion.version", cascade="all, delete-orphan"
    )
    test_runs: Mapped[list["TestRun"]] = relationship(order_by="TestRun.id", cascade="all, delete-orphan")
    approvals: Mapped[list["Approval"]] = relationship(order_by="Approval.id", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(order_by="Event.id", cascade="all, delete-orphan")


class ScriptVersion(Base):
    __tablename__ = "script_versions"
    __table_args__ = (UniqueConstraint("runbook_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbooks.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    author: Mapped[str] = mapped_column(String(32))
    feedback: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), default="bash")
    script: Mapped[str] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(Json, default=list)
    notes: Mapped[list] = mapped_column(Json, default=list)
    lint: Mapped[dict] = mapped_column(Json)

    runbook: Mapped[Runbook] = relationship(back_populates="scripts")


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbooks.id", ondelete="CASCADE"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    script_version: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    passed: Mapped[bool] = mapped_column(Boolean)
    failed_stage: Mapped[str | None] = mapped_column(String(16))
    lint_passed: Mapped[bool] = mapped_column(Boolean)
    dry_run: Mapped[dict | None] = mapped_column(Json)
    execute: Mapped[dict | None] = mapped_column(Json)
    diagnosis: Mapped[dict | None] = mapped_column(Json)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbooks.id", ondelete="CASCADE"), index=True)
    reviewer: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(Text)
    script_version: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    """The live activity log shown in the web app, and the audit trail."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbooks.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    agent: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(16), default="info")


class Job(Base):
    """Work queue for the worker process (claimed with SELECT ... FOR UPDATE SKIP LOCKED)."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbooks.id", ondelete="CASCADE"), index=True)
    payload: Mapped[dict] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    locked_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerHeartbeat(Base):
    """Each worker reports in regularly, so the API knows whether workers and the sandbox are up."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    sandbox_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    sandbox_detail: Mapped[str | None] = mapped_column(Text)



ROLES = ("submitter", "approver", "operator", "admin")


class User(Base):
    """A person who signs in, either with a local password or with Microsoft Entra ID."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    auth_provider: Mapped[str] = mapped_column(String(16), default="local")  # local | entra
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)  # Entra object id
    password_hash: Mapped[str | None] = mapped_column(String(255))
    roles: Mapped[list] = mapped_column(Json, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Who did what, when: sign-ins, uploads, approvals, runs, user and server changes."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(Json, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))


# ---------- Phase 3: running approved scripts on real servers ----------

class Credential(Base):
    """An SSH key or password. The secret is encrypted at rest and never returned by the API."""

    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[str] = mapped_column(String(16))  # ssh_key | password
    username: Mapped[str] = mapped_column(String(128))
    encrypted_secret: Mapped[str] = mapped_column(Text)
    encrypted_passphrase: Mapped[str | None] = mapped_column(Text)
    public_fingerprint: Mapped[str | None] = mapped_column(String(128))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    hostname: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=22)
    os: Mapped[str] = mapped_column(String(16), default="linux")
    group_name: Mapped[str | None] = mapped_column(String(128), index=True)  # e.g. a client account or environment
    credential_id: Mapped[int | None] = mapped_column(ForeignKey("credentials.id", ondelete="SET NULL"))
    host_key: Mapped[str | None] = mapped_column(Text)  # "<type> <base64>", pinned after the first verified connection
    host_key_fingerprint: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_check_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScriptRun(Base):
    """One run of an approved script on one server."""

    __tablename__ = "script_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbooks.id", ondelete="CASCADE"), index=True)
    script_version: Mapped[int] = mapped_column(Integer)
    script_sha256: Mapped[str] = mapped_column(String(64))
    server_id: Mapped[int | None] = mapped_column(ForeignKey("servers.id", ondelete="SET NULL"), index=True)
    server_name: Mapped[str] = mapped_column(String(128))
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    requested_by_name: Mapped[str] = mapped_column(String(255))
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual | schedule | alert
    trigger_ref: Mapped[int | None] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))  # dry_run | execute
    ticket: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[float | None] = mapped_column()
    exit_code: Mapped[int | None] = mapped_column(Integer)
    dry_run_passed: Mapped[bool | None] = mapped_column(Boolean)
    steps: Mapped[list] = mapped_column(Json, default=list)
    output: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbooks.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    cron: Mapped[str] = mapped_column(String(64))  # UTC
    server_ids: Mapped[list] = mapped_column(Json, default=list)
    mode: Mapped[str] = mapped_column(String(16), default="execute")
    ticket: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Trigger(Base):
    """A webhook that monitoring can call to start an approved script (e.g. on a 'disk full' alert)."""

    __tablename__ = "triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbooks.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    server_ids: Mapped[list] = mapped_column(Json, default=list)
    mode: Mapped[str] = mapped_column(String(16), default="execute")
    token_hash: Mapped[str] = mapped_column(String(64))
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=5)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
