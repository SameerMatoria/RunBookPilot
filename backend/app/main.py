"""RunbookPilot backend API.

Agent work (parse, write, test, review) and script runs are queued and done by the worker process
(app.worker). Every route except /health and sign-in needs a signed-in user; see app/auth.py.
"""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, heartbeat, metrics
from .auth import current_user
from .routes import auth_routes, runbooks, servers, users
from .routes import runs as runs_routes

app = FastAPI(title="RunbookPilot API")
# The web app is served from the same origin in production (nginx forwards /api); this allows the
# Vite dev server. Cookies need explicit origins, not "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(runbooks.router)
app.include_router(users.router)
app.include_router(servers.router)
app.include_router(runs_routes.router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "model": config.LLM_MODEL,
        "key_configured": bool(config.LLM_API_KEY),
        "fallback_model": config.LLM_FALLBACK_MODEL if config.LLM_FALLBACK_API_KEY else None,
    }


@app.get("/sandbox")
def sandbox_status(user: dict = Depends(current_user)):
    """Reported by the workers (they run the sandbox; the API never talks to Docker)."""
    return heartbeat.status()


@app.get("/metrics")
def get_metrics(user: dict = Depends(current_user)):
    return metrics.compute()
