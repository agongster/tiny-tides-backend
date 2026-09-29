"""Tiny Tides multiplayer API.

Step 1 of the multiplayer plan: a deployed service with a health check, so the
Render + Neon + GitHub Pages wiring is proven before any game features exist.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import ALLOWED_ORIGINS, JWT_SECRET, USING_SQLITE_FALLBACK
from .database import engine

app = FastAPI(title="Tiny Tides API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # any localhost port, for running the game locally
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    """Reports whether the API is up and can reach its database.

    Always answers 200 so a sleeping-then-waking Render instance is easy to
    tell apart from a broken database: check the "database" field.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "sqlite (local fallback)" if USING_SQLITE_FALLBACK else "connected"
    except Exception as exc:  # report, don't crash, so the problem is visible
        database = f"error: {type(exc).__name__}"
    return {
        "status": "ok",
        "database": database,
        "jwt_secret": "set" if JWT_SECRET else "missing",
        "allowed_origins": ALLOWED_ORIGINS,
    }


@app.get("/")
def root() -> dict:
    return {"name": "Tiny Tides API", "health": "/api/health", "docs": "/docs"}
