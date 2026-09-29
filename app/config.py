"""Runtime configuration, read once from environment variables.

Secrets (the database password, the token signing key) only ever come from the
environment: Render's Environment tab in production, a git-ignored .env file
locally. See .env.example.
"""

import os
import secrets

from dotenv import load_dotenv

load_dotenv()


def _normalize_database_url(url: str) -> str:
    """Neon hands out postgres:// or postgresql:// URLs; SQLAlchemy 2 with
    psycopg 3 needs the driver named explicitly."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


_raw_database_url = os.getenv("DATABASE_URL", "").strip()

# No DATABASE_URL means local development: fall back to a SQLite file so the
# project runs without installing Postgres.
USING_SQLITE_FALLBACK = not _raw_database_url
DATABASE_URL = (
    "sqlite:///./tiny_tides.db" if USING_SQLITE_FALLBACK else _normalize_database_url(_raw_database_url)
)

_raw_secret = os.getenv("JWT_SECRET", "").strip()
if _raw_secret:
    JWT_SECRET = _raw_secret
elif USING_SQLITE_FALLBACK:
    # Local development: a throwaway key. Logins stop working after a restart,
    # which is fine on a laptop.
    JWT_SECRET = secrets.token_urlsafe(48)
    JWT_SECRET_IS_THROWAWAY = True
else:
    # A real database means a real deployment: refuse to sign login tokens with
    # a key anyone could guess.
    raise RuntimeError(
        "JWT_SECRET must be set when DATABASE_URL points at a real database. "
        'Generate one with: python3 -c "import secrets; print(secrets.token_urlsafe(48))"'
    )
JWT_SECRET_IS_THROWAWAY = not _raw_secret
TOKEN_DAYS = int(os.getenv("TOKEN_DAYS", "30"))

# The whole game save is stored as one JSON document; this caps its size so the
# endpoint can't be used as free file storage.
MAX_SAVE_BYTES = int(os.getenv("MAX_SAVE_BYTES", "200000"))

# Browsers never send a trailing slash in the Origin header, so one typed into
# the Render dashboard would match nothing and silently fail every request.
ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", "https://agongster.github.io").split(",")
    if origin.strip().rstrip("/")
]
