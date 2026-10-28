"""Audit log: who did what, when."""
from fastapi import Request
from sqlalchemy import select

from .db import session_scope
from .models import AuditLog


def record(user: dict | None, action: str, target_type: str | None = None, target_id=None,
           request: Request | None = None, **details) -> None:
    with session_scope() as s:
        s.add(AuditLog(
            user_id=user["id"] if user else None,
            username=user["username"] if user else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details,
            ip=request.client.host if request and request.client else None,
        ))


def recent(limit: int = 200, action: str | None = None, username: str | None = None, before_id: int | None = None) -> list[dict]:
    with session_scope() as s:
        query = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))
        if action:
            query = query.where(AuditLog.action.like(f"{action}%"))
        if username:
            query = query.where(AuditLog.username == username.lower())
        if before_id:
            query = query.where(AuditLog.id < before_id)
        return [
            {"id": a.id, "at": a.at.isoformat(), "username": a.username, "action": a.action,
             "target_type": a.target_type, "target_id": a.target_id, "details": a.details or {}, "ip": a.ip}
            for a in s.scalars(query)
        ]
