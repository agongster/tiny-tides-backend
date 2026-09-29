"""Runtime configuration, read once from environment variables.

Secrets (the database password, the token signing key) only ever come from the
environment: Render's Environment tab in production, a git-ignored .env file
locally. See .env.example.
"""

import os

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

JWT_SECRET = os.getenv("JWT_SECRET", "").strip()

# Browsers never send a trailing slash in the Origin header, so one typed into
# the Render dashboard would match nothing and silently fail every request.
ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", "https://agongster.github.io").split(",")
    if origin.strip().rstrip("/")
]
