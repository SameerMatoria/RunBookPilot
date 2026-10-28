"""User management (admins) and the audit log."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from .. import audit, auth
from ..db import session_scope
from ..models import User

router = APIRouter(tags=["users"])


@router.get("/users")
def list_users(user: dict = Depends(auth.require("admin"))):
    with session_scope() as s:
        return [auth.user_dict(u) for u in s.scalars(select(User).order_by(User.username))]


@router.get("/users/directory")
def directory(user: dict = Depends(auth.current_user)):
    """Names and roles only, so anyone can see who can approve."""
    with session_scope() as s:
        return [{"id": u.id, "display_name": u.display_name, "roles": u.roles}
                for u in s.scalars(select(User).where(User.active.is_(True)).order_by(User.display_name))]


class NewUser(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: str | None = None
    roles: list[str] = ["submitter"]


@router.post("/users")
def create_user(body: NewUser, request: Request, admin: dict = Depends(auth.require("admin"))):
    user = auth.create_local_user(body.username, body.password, body.display_name, body.roles, body.email)
    audit.record(admin, "user.create", "user", user["id"], request, username=user["username"], roles=user["roles"])
    return user


class UserUpdate(BaseModel):
    display_name: str | None = None
    roles: list[str] | None = None
    active: bool | None = None
    password: str | None = None


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, admin: dict = Depends(auth.require("admin"))):
    changes = body.model_dump(exclude_none=True)
    if user_id == admin["id"] and (changes.get("active") is False or ("roles" in changes and "admin" not in changes["roles"])):
        raise HTTPException(400, "You can't remove your own admin access or disable yourself.")
    with session_scope() as s:
        user = s.get(User, user_id)
        if user is None:
            raise HTTPException(404, "User not found")
        if "display_name" in changes:
            user.display_name = changes["display_name"]
        if "roles" in changes:
            user.roles = auth.clean_roles(changes["roles"])
        if "active" in changes:
            user.active = changes["active"]
        if "password" in changes:
            if user.auth_provider != "local":
                raise HTTPException(400, "Microsoft accounts don't have a password here.")
            if len(changes["password"]) < 8:
                raise HTTPException(400, "The password must be at least 8 characters.")
            user.password_hash = auth.hash_password(changes["password"])
        s.flush()
        result = auth.user_dict(user)
    logged = {k: v for k, v in changes.items() if k != "password"} | ({"password_reset": True} if "password" in changes else {})
    audit.record(admin, "user.update", "user", user_id, request, **logged)
    return result


@router.get("/audit")
def audit_log(limit: int = 200, action: str | None = None, username: str | None = None, before_id: int | None = None,
              user: dict = Depends(auth.require("admin"))):
    return audit.recent(limit=limit, action=action, username=username, before_id=before_id)
