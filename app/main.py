"""Tiny Tides multiplayer API.

Step 2 of the plan: accounts with unique usernames, and cloud saves.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import models  # noqa: F401  (registers the tables)
from .config import ALLOWED_ORIGINS, JWT_SECRET_IS_THROWAWAY, USING_SQLITE_FALLBACK
from .database import Base, engine
from .routers import auth, saves

# Creates any missing tables on startup. It never alters an existing table, so
# later column changes will need a small migration.
Base.metadata.create_all(engine)

app = FastAPI(title="Tiny Tides API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # any localhost port, for running the game locally
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(saves.router)


@app.get("/api/health")
def health() -> dict:
    """Reports whether the API is up and can reach its database.

    Always answers 200 so a waking Render instance is easy to tell apart from a
    broken database: check the "database" field.
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
        "jwt_secret": "throwaway (local)" if JWT_SECRET_IS_THROWAWAY else "set",
        "allowed_origins": ALLOWED_ORIGINS,
    }


@app.get("/")
def root() -> dict:
    return {"name": "Tiny Tides API", "health": "/api/health", "docs": "/docs"}
