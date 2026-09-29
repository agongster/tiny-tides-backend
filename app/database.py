"""Database engine, session factory, and the FastAPI session dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL, USING_SQLITE_FALLBACK

# Neon closes idle connections and Render's free tier sleeps, so check a pooled
# connection is alive before using it rather than failing the first request.
engine_kwargs: dict = {"pool_pre_ping": True}
if USING_SQLITE_FALLBACK:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_recycle"] = 300

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class every ORM model inherits from."""


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
