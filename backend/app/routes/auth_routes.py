"""Sign-in, sign-out, and the current user."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import audit, auth, config

router = APIRouter(prefix="/auth", tags=["auth"])


def _start_session(response: Response, user: dict) -> dict:
    token = auth.create_session_token(user)
    response.set_cookie(auth.COOKIE_NAME, token, httponly=True, samesite="lax", secure=config.COOKIE_SECURE,
                        max_age=config.SESSION_HOURS * 3600, path="/")
    return {"user": user, "token": token}


@router.get("/config")
def auth_config():
    """What the sign-in page should offer."""
    return {
        "local": True,
        "entra": auth.entra_enabled(),
        "entra_client_id": config.ENTRA_CLIENT_ID or None,
        "entra_tenant_id": config.ENTRA_TENANT_ID or None,
        "needs_setup": auth.user_count() == 0,
    }


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    user = auth.authenticate_local(body.username, body.password)
    if user is None:
        audit.record(None, "auth.login_failed", "user", None, request, username=body.username.strip().lower())
        raise HTTPException(401, "Wrong username or password.")
    audit.record(user, "auth.login", "user", user["id"], request, provider="local")
    return _start_session(response, user)


class EntraIn(BaseModel):
    id_token: str


@router.post("/entra")
def login_entra(body: EntraIn, request: Request, response: Response):
    if not auth.entra_enabled():
        raise HTTPException(400, "Microsoft sign-in is not configured.")
    user = auth.upsert_entra_user(auth.verify_entra_token(body.id_token))
    audit.record(user, "auth.login", "user", user["id"], request, provider="entra")
    return _start_session(response, user)


class SetupIn(BaseModel):
    username: str
    password: str
    display_name: str | None = None


@router.post("/setup")
def first_admin(body: SetupIn, request: Request, response: Response):
    """Create the first admin. Only works while there are no users at all."""
    if auth.user_count() > 0:
        raise HTTPException(409, "Setup is already done. Ask an admin for an account.")
    user = auth.create_local_user(body.username, body.password, body.display_name, roles=("admin",))
    audit.record(user, "auth.setup", "user", user["id"], request)
    return _start_session(response, user)


@router.post("/logout")
def logout(request: Request, response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(auth.current_user)):
    return user
