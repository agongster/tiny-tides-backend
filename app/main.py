"""Tiny Tides multiplayer API: accounts, cloud saves, friends, visiting,
gifts, and live rooms for fishing together."""

import logging
import os
import secrets

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import models  # noqa: F401  (registers the tables)
from .config import ALLOWED_ORIGINS, JWT_SECRET_IS_THROWAWAY, USING_SQLITE_FALLBACK
from .database import Base, engine
from . import realtime
from .routers import auth, friends, gifts, saves, worlds

# Creates any missing tables on startup. It never alters an existing table, so
# later column changes will need a small migration.
Base.metadata.create_all(engine)

# Live rooms and "who's online" are kept in this process's memory, so the API
# must run as ONE process. uvicorn quietly starts several when WEB_CONCURRENCY
# is set, and then friends in different processes can't see each other.
WORKERS = os.getenv("WEB_CONCURRENCY", "1")
# A random name for this running copy. Process ids repeat across containers
# (every instance can be pid 55), so this is what tells instances apart.
INSTANCE = secrets.token_hex(4)
if WORKERS != "1":
    logging.getLogger("uvicorn.error").warning(
        "WEB_CONCURRENCY=%s: multiplayer needs a single process. Add --workers 1 "
        "to the start command.", WORKERS,
    )

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
app.include_router(friends.router)
app.include_router(worlds.router)
app.include_router(gifts.router)
app.include_router(realtime.router)


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
        # should stay the same across refreshes; if it changes, more than one
        # copy of the server is running and multiplayer will split between them
        "instance": INSTANCE,
        "web_concurrency": WORKERS,
    }


@app.get("/")
def root() -> dict:
    return {"name": "Tiny Tides API", "health": "/api/health", "docs": "/docs"}
