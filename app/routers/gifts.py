"""Sending coins and fish to friends, and claiming the ones sent to you.

Coins only ever move inside the database, with a single conditional UPDATE, so
two gifts sent at once can't spend the same coins twice. Every change bumps the
save's version, which tells the sender's and recipient's games to adopt the new
balance instead of overwriting it.

Fish work the same way: sending takes the fish out of the sender's saved
bucket or tank (the game uploads first so the server can see it), and
claiming puts it into the recipient's save, bucket first, then tank.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import BUCKET_CAPS, FISH_GIFT_DAILY_LIMIT, GIFT_DAILY_LIMIT, GIFT_MAX, UNGIFTABLE_FISH
from ..database import get_db
from ..models import FishGift, Gift, Save, User
from ..realtime import hub
from ..security import current_user
from ..social import are_friends, user_by_name

router = APIRouter(prefix="/api/gifts", tags=["gifts"])


class FishGiftIn(BaseModel):
    to: str
    uid: int
    note: str = Field(default="", max_length=60)


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


def _fish_out(db: Session, g: FishGift, other_id: int) -> dict:
    other = db.get(User, other_id)
    return {"id": g.id, "username": other.username if other else "?", "fish": g.fish, "note": g.note,
            "sent_at": g.created_at, "claimed": g.claimed_at is not None}


def _fish_sent_today(db: Session, user_id: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.scalar(select(func.count(FishGift.id)).where(FishGift.from_id == user_id, FishGift.created_at >= since)) or 0


@router.post("/fish", status_code=status.HTTP_201_CREATED)
async def send_fish(body: FishGiftIn, me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    to = user_by_name(db, body.to)
    if to is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    if to.id == me.id or not are_friends(db, me.id, to.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_friends")
    if _fish_sent_today(db, me.id) >= FISH_GIFT_DAILY_LIMIT:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, {"error": "fish_daily_limit", "limit": FISH_GIFT_DAILY_LIMIT})
    mine = db.scalar(select(Save).where(Save.user_id == me.id).with_for_update())
    data = dict(mine.data or {}) if mine else {}
    fish, where = None, None
    for key in ("bucket", "aquarium"):
        stash = list(data.get(key) or [])
        for i, c in enumerate(stash):
            if isinstance(c, dict) and c.get("uid") == body.uid:
                fish, where = stash.pop(i), key
                data[key] = stash
                break
        if fish:
            break
    if fish is None:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_such_fish")
    if fish.get("id") in UNGIFTABLE_FISH:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cant_gift_that")
    mine.data = data  # a new dict, so the JSON column notices the change
    mine.version += 1
    mine.updated_at = datetime.now(timezone.utc)
    kept = {k: fish.get(k) for k in ("id", "size", "stars", "value")}
    db.add(FishGift(from_id=me.id, to_id=to.id, fish=kept, note=body.note.strip()))
    db.commit()
    await hub.notify(to.id, {"t": "fish_gift", "from": me.username, "fish": kept["id"]})
    return {"version": mine.version, "from": where, "remaining_today": FISH_GIFT_DAILY_LIMIT - _fish_sent_today(db, me.id)}


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
    fish_received = db.scalars(select(FishGift).where(FishGift.to_id == me.id).order_by(FishGift.created_at.desc()).limit(15)).all()
    fish_sent = db.scalars(select(FishGift).where(FishGift.from_id == me.id).order_by(FishGift.created_at.desc()).limit(15)).all()
    return {
        "received": [_gift_out(db, g, g.from_id) for g in received],
        "sent": [_gift_out(db, g, g.to_id) for g in sent],
        "fish_received": [_fish_out(db, g, g.from_id) for g in fish_received],
        "fish_sent": [_fish_out(db, g, g.to_id) for g in fish_sent],
        "remaining_today": max(0, GIFT_DAILY_LIMIT - _sent_today(db, me.id)),
        "fish_remaining_today": max(0, FISH_GIFT_DAILY_LIMIT - _fish_sent_today(db, me.id)),
    }


@router.post("/claim")
def claim(me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    mine = db.get(Save, me.id)
    if mine is None:
        # nowhere to put gifts yet; they stay waiting until the first upload
        return {"claimed": [], "fish": [], "coins": 0, "version": 0}
    waiting = db.scalars(
        select(Gift).where(Gift.to_id == me.id, Gift.claimed_at.is_(None)).with_for_update()
    ).all()
    fish_waiting = db.scalars(
        select(FishGift).where(FishGift.to_id == me.id, FishGift.claimed_at.is_(None)).with_for_update()
    ).all()
    if not waiting and not fish_waiting:
        return {"claimed": [], "fish": [], "coins": mine.coins, "version": mine.version}
    now = datetime.now(timezone.utc)
    total = 0
    for g in waiting:
        g.claimed_at = now
        total += g.amount
    # fish go in the bucket while there's room, then the tank; each gets the
    # save's next uid, and the game is told exactly where each one went
    placed = []
    if fish_waiting:
        data = dict(mine.data or {})
        bucket, tank = list(data.get("bucket") or []), list(data.get("aquarium") or [])
        level = data.get("bucketLvl") if isinstance(data.get("bucketLvl"), int) else 0
        cap = BUCKET_CAPS[max(0, min(level, len(BUCKET_CAPS) - 1))]
        next_uid = int(data.get("nextUid") or 1)
        for g in fish_waiting:
            g.claimed_at = now
            fish = {**g.fish, "uid": next_uid}
            next_uid += 1
            where = "bucket" if len(bucket) < cap else "tank"
            (bucket if where == "bucket" else tank).append(fish)
            placed.append({**_fish_out(db, g, g.from_id), "fish": fish, "where": where})
        data["bucket"], data["aquarium"], data["nextUid"] = bucket, tank, next_uid
        mine.data = data
    mine.coins += total
    mine.version += 1
    mine.updated_at = now
    db.commit()
    db.refresh(mine)
    return {
        "claimed": [_gift_out(db, g, g.from_id) for g in waiting],
        "fish": placed,
        "coins": mine.coins,
        "version": mine.version,
    }
