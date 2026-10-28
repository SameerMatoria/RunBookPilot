"""Accounts for trusted command-line scripts (benchmark, smoke tests) that run on the server itself.

They have direct database access anyway, so they get a signed session token without a password
(the account's password is random and never shown, so nobody can sign in with it interactively).
"""
import secrets

from fastapi.testclient import TestClient
from sqlalchemy import select

from . import auth
from .db import session_scope
from .models import User


def service_user(username: str, roles: tuple[str, ...], display_name: str) -> dict:
    with session_scope() as s:
        user = s.scalar(select(User).where(User.username == username))
        if user:
            return auth.user_dict(user)
    return auth.create_local_user(username, secrets.token_urlsafe(32), display_name, roles)


def client_for(username: str, roles: tuple[str, ...], display_name: str) -> TestClient:
    from .main import app

    user = service_user(username, roles, display_name)
    token = auth.create_session_token(user)
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})
