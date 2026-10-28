"""Sign-in and permissions.

- Local accounts: passwords hashed with scrypt.
- Microsoft Entra ID: the web app signs in with Microsoft and sends us the ID token; we verify its
  signature against Microsoft's published keys before trusting it.
- Sessions: a signed token in an HttpOnly cookie (browsers) or an Authorization: Bearer header (scripts).
- Roles: submitter, approver, operator, admin. Admins can do everything.
"""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select

from . import config
from .db import session_scope
from .models import ROLES, User

COOKIE_NAME = "rbp_session"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


# ---------- passwords ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_b64, digest_b64 = stored.split("$")
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


# ---------- users ----------

def user_dict(user: User) -> dict:
    return {
        "id": user.id, "username": user.username, "display_name": user.display_name, "email": user.email,
        "auth_provider": user.auth_provider, "roles": list(user.roles or []), "active": user.active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def clean_roles(roles) -> list[str]:
    unknown = set(roles) - set(ROLES)
    if unknown:
        raise HTTPException(400, f"Unknown role(s): {', '.join(sorted(unknown))}. Use: {', '.join(ROLES)}")
    return [r for r in ROLES if r in roles]


def create_local_user(username: str, password: str, display_name: str | None = None, roles=("submitter",),
                      email: str | None = None) -> dict:
    username = username.strip().lower()
    if not username or len(password) < 8:
        raise HTTPException(400, "Username is required and the password must be at least 8 characters.")
    with session_scope() as s:
        if s.scalar(select(User).where(func.lower(User.username) == username)):
            raise HTTPException(409, f"User {username} already exists.")
        user = User(username=username, display_name=display_name or username, email=email,
                    auth_provider="local", password_hash=hash_password(password), roles=clean_roles(roles),
                    active=True)
        s.add(user)
        s.flush()
        return user_dict(user)


def authenticate_local(username: str, password: str) -> dict | None:
    with session_scope() as s:
        user = s.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
        if user is None or not user.active or user.auth_provider != "local":
            hash_password(password)  # spend the same time, so usernames can't be probed by timing
            return None
        if not verify_password(password, user.password_hash):
            return None
        user.last_login_at = datetime.now(timezone.utc)
        return user_dict(user)


def get_user(user_id: int) -> dict | None:
    with session_scope() as s:
        user = s.get(User, user_id)
        return user_dict(user) if user else None


def user_count() -> int:
    with session_scope() as s:
        return s.scalar(select(func.count(User.id))) or 0


# ---------- Microsoft Entra ID ----------

def entra_enabled() -> bool:
    return bool(config.ENTRA_TENANT_ID and config.ENTRA_CLIENT_ID)


@lru_cache(maxsize=1)
def _entra_keys() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"https://login.microsoftonline.com/{config.ENTRA_TENANT_ID}/discovery/v2.0/keys")


def verify_entra_token(id_token: str, signing_key=None) -> dict:
    """Check the token was issued by our tenant for our app; returns its claims."""
    key = signing_key or _entra_keys().get_signing_key_from_jwt(id_token).key
    try:
        return jwt.decode(
            id_token, key, algorithms=["RS256"], audience=config.ENTRA_CLIENT_ID,
            issuer=f"https://login.microsoftonline.com/{config.ENTRA_TENANT_ID}/v2.0",
        )
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Microsoft sign-in token rejected: {e}")


def upsert_entra_user(claims: dict) -> dict:
    """Find or create the user for a verified Entra token. App roles in the token (if the app
    registration defines them) are synced on every sign-in; otherwise roles are managed here."""
    oid = claims["oid"]
    username = (claims.get("preferred_username") or claims.get("email") or oid).lower()
    token_roles = [r.lower() for r in claims.get("roles", []) if r.lower() in ROLES]
    with session_scope() as s:
        user = s.scalar(select(User).where(User.external_id == oid))
        if user is None:
            user = User(username=username, display_name=claims.get("name") or username, email=claims.get("email"),
                        auth_provider="entra", external_id=oid, active=True,
                        roles=clean_roles(token_roles or config.ENTRA_DEFAULT_ROLES))
            s.add(user)
        elif token_roles:
            user.roles = clean_roles(token_roles)
        if not user.active:
            raise HTTPException(403, "This account is disabled.")
        user.display_name = claims.get("name") or user.display_name
        user.last_login_at = datetime.now(timezone.utc)
        s.flush()
        return user_dict(user)


# ---------- sessions ----------

def create_session_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user["id"]), "iat": now, "exp": now + timedelta(hours=config.SESSION_HOURS)}
    return jwt.encode(claims, config.SECRET_KEY, algorithm="HS256")


def _token_from(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(COOKIE_NAME)


def current_user(request: Request) -> dict:
    """FastAPI dependency: the signed-in, active user (401 otherwise)."""
    token = _token_from(request)
    if not token:
        raise HTTPException(401, "Sign in required.")
    try:
        claims = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Your session has expired. Sign in again.")
    user = get_user(int(claims["sub"]))
    if user is None or not user["active"]:
        raise HTTPException(401, "Account not found or disabled.")
    return user


def has_role(user: dict, role: str) -> bool:
    return "admin" in user["roles"] or role in user["roles"]


def require(*roles: str):
    """FastAPI dependency factory: the user must have at least one of these roles (admins always pass)."""

    def check(user: dict = Depends(current_user)) -> dict:
        if not any(has_role(user, r) for r in roles):
            raise HTTPException(403, f"This needs the {' or '.join(roles)} role.")
        return user

    return check
