"""Sending coins to friends, and claiming the ones sent to you.

Coins only ever move inside the database, with a single conditional UPDATE, so
two gifts sent at once can't spend the same coins twice. Every change bumps the
save's version, which tells the sender's and recipient's games to adopt the new
balance instead of overwriting it.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import GIFT_DAILY_LIMIT, GIFT_MAX
from ..database import get_db
from ..models import Gift, Save, User
from ..realtime import hub
from ..security import current_user
from ..social import are_friends, user_by_name

router = APIRouter(prefix="/api/gifts", tags=["gifts"])


class GiftIn(BaseModel):
    to: str
    amount: int = Field(ge=1, le=GIFT_MAX)
    note: str = Field(default="", max_length=60)


def _sent_today(db: Session, user_id: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.scalar(select(func.coalesce(func.sum(Gift.amount), 0)).where(Gift.from_id == user_id, Gift.created_at >= since)) or 0


def _gift_out(db: Session, g: Gift, other_id: int) -> dict:
    other = db.get(User, other_id)
    return {"id": g.id, "username": other.username if other else "?", "amount": g.amount, "note": g.note,
            "sent_at": g.created_at, "claimed": g.claimed_at is not None}


@router.post("", status_code=status.HTTP_201_CREATED)
async def send(body: GiftIn, me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    to = user_by_name(db, body.to)
    if to is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    if to.id == me.id or not are_friends(db, me.id, to.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_friends")
    remaining = GIFT_DAILY_LIMIT - _sent_today(db, me.id)
    if body.amount > remaining:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, {"error": "daily_limit", "remaining": max(0, remaining)})
    taken = db.execute(
        update(Save)
        .where(Save.user_id == me.id, Save.coins >= body.amount)
        .values(coins=Save.coins - body.amount, version=Save.version + 1, updated_at=datetime.now(timezone.utc))
    ).rowcount
    if taken != 1:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "not_enough_coins")
    db.add(Gift(from_id=me.id, to_id=to.id, amount=body.amount, note=body.note.strip()))
    db.commit()
    mine = db.get(Save, me.id)
    db.refresh(mine)
    await hub.notify(to.id, {"t": "gift", "from": me.username, "amount": body.amount})
    return {"coins": mine.coins, "version": mine.version, "remaining_today": remaining - body.amount}


@router.get("")
def history(me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    received = db.scalars(select(Gift).where(Gift.to_id == me.id).order_by(Gift.created_at.desc()).limit(15)).all()
    sent = db.scalars(select(Gift).where(Gift.from_id == me.id).order_by(Gift.created_at.desc()).limit(15)).all()
    return {
        "received": [_gift_out(db, g, g.from_id) for g in received],
        "sent": [_gift_out(db, g, g.to_id) for g in sent],
        "remaining_today": max(0, GIFT_DAILY_LIMIT - _sent_today(db, me.id)),
    }


@router.post("/claim")
def claim(me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    mine = db.get(Save, me.id)
    if mine is None:
        # nowhere to put coins yet; they stay waiting until the first upload
        return {"claimed": [], "coins": 0, "version": 0}
    waiting = db.scalars(
        select(Gift).where(Gift.to_id == me.id, Gift.claimed_at.is_(None)).with_for_update()
    ).all()
    if not waiting:
        return {"claimed": [], "coins": mine.coins, "version": mine.version}
    now = datetime.now(timezone.utc)
    total = 0
    for g in waiting:
        g.claimed_at = now
        total += g.amount
    db.execute(
        update(Save).where(Save.user_id == me.id)
        .values(coins=Save.coins + total, version=Save.version + 1, updated_at=now)
    )
    db.commit()
    db.refresh(mine)
    return {
        "claimed": [_gift_out(db, g, g.from_id) for g in waiting],
        "coins": mine.coins,
        "version": mine.version,
    }
