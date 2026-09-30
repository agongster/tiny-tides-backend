"""Helpers shared by the friends, worlds, gifts and realtime code."""

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .models import Friendship, User


def pair_row(db: Session, a: int, b: int) -> Friendship | None:
    """The friendship row between two players, whichever of them asked."""
    return db.scalar(
        select(Friendship).where(
            or_(
                and_(Friendship.requester_id == a, Friendship.addressee_id == b),
                and_(Friendship.requester_id == b, Friendship.addressee_id == a),
            )
        )
    )


def are_friends(db: Session, a: int, b: int) -> bool:
    row = pair_row(db, a, b)
    return row is not None and row.status == "accepted"


def user_by_name(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username_key == username.strip().lower()))


def as_utc(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; Postgres gives aware ones."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
