import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")

# Primary model: any OpenAI-compatible endpoint (Groq by default).
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# More models on the same provider, tried in order when a model's daily quota is used up or a
# request is too large for it. On Groq every model has its own quota, so this multiplies capacity.
LLM_FALLBACK_MODELS = [m.strip() for m in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if m.strip()]

# How hard gpt-oss reasoning models think before answering: low, medium or high.
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "medium")

# Optional preferred model per agent, e.g. a smaller model for the Parser to save the main model's
# quota for the Author. Unset agents use LLM_MODEL.
LLM_AGENT_MODELS = {
    agent: os.getenv(f"LLM_MODEL_{agent.upper()}", "")
    for agent in ("parser", "author", "tester", "reviewer")
}

# Optional backup model, used automatically if the primary fails (e.g. rate limit during the demo).
LLM_FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "")
LLM_FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY", "")
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "")

# Database: Postgres (docker compose up -d db). Tests use SQLite.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://runbookpilot:runbookpilot@localhost:5432/runbookpilot")

# Optional explicit path to docker; otherwise found on PATH or in Docker Desktop's install folder.
DOCKER_BIN = os.getenv("DOCKER_BIN", "")

DATA_DIR = PROJECT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _persistent_secret(name: str, make) -> str:
    """Use the environment variable if set; otherwise create one once and keep it in data/ (dev only).
    In production, set it explicitly (Azure: from Key Vault)."""
    if value := os.getenv(name):
        return value
    path = DATA_DIR / f".{name.lower()}"
    if not path.exists():
        path.write_text(make(), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def _random_key() -> str:
    import secrets

    return secrets.token_urlsafe(48)


def _fernet_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


# Signs session tokens. Changing it signs everyone out.
SECRET_KEY = _persistent_secret("SECRET_KEY", _random_key)
# Encrypts stored server credentials. Losing it makes saved credentials unreadable: back it up.
MASTER_KEY = _persistent_secret("MASTER_KEY", _fernet_key)

SESSION_HOURS = int(os.getenv("SESSION_HOURS", "12"))
# A script run on a real server is stopped after this long.
RUN_TIMEOUT_SECONDS = int(os.getenv("RUN_TIMEOUT_SECONDS", "600"))
# Mark session cookies Secure (HTTPS only). Turn on in production.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# Microsoft Entra ID sign-in (optional). Needs an app registration; see README.
ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID", "")
ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "")
# Roles for Entra users on first sign-in when the token carries no app roles.
ENTRA_DEFAULT_ROLES = [r.strip() for r in os.getenv("ENTRA_DEFAULT_ROLES", "submitter").split(",") if r.strip()]
