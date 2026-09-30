"""Database tables."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # stored lowercased, so "April@x.com" and "april@x.com" are one account
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    # shown exactly as the player typed it...
    username: Mapped[str] = mapped_column(String(16))
    # ...but unique case-insensitively, so "April" and "april" can't both exist
    username_key: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Save(Base):
    """One cloud save per player.

    Coins live in their own column (not only inside `data`) so that gifting can
    later move them with a single conditional UPDATE that can never overdraw.
    `version` goes up by one on every write; a write must say which version it
    was based on, so a stale tab can't overwrite newer progress.
    """

    __tablename__ = "saves"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    coins: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Friendship(Base):
    """One row per pair of players. `requester` asked; `addressee` answers.

    status is "pending" until the addressee accepts, then "accepted". Declining
    or removing a friend deletes the row, so they can ask again later.
    """

    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("requester_id", "addressee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    addressee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Gift(Base):
    """Coins sent to a friend. They sit here until the recipient claims them."""

    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    to_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
