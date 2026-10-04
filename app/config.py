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

# ---- multiplayer limits
GIFT_MAX = int(os.getenv("GIFT_MAX", "1000"))            # most coins in one gift
GIFT_DAILY_LIMIT = int(os.getenv("GIFT_DAILY_LIMIT", "2000"))  # per sender, rolling 24h
FISH_GIFT_DAILY_LIMIT = int(os.getenv("FISH_GIFT_DAILY_LIMIT", "20"))  # fish per sender, rolling 24h
# Bucket sizes by upgrade level (mirrors BUCKETS in the game's data.js), so a
# claimed fish lands in the bucket if there's room and the tank otherwise.
BUCKET_CAPS = (6, 12, 24, 40, 64)
# Fish that can't be given away. (LeBron used to be here; he can be gifted now,
# though he still can't be sold.)
UNGIFTABLE_FISH: set[str] = set()
ROOM_SIZE = int(os.getenv("ROOM_SIZE", "4"))             # host + 3 visitors

# A save may only gain this many coins, plus COIN_RATE per second since its last
# upload. Real fishing can't beat it; typing a big number into the console can.
COIN_JUMP_BASE = int(os.getenv("COIN_JUMP_BASE", "5000"))
COIN_RATE = int(os.getenv("COIN_RATE", "300"))
