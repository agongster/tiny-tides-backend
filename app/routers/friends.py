"""Friend requests and the friends list."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Friendship, User
from ..realtime import hub
from ..security import current_user
from ..social import pair_row, user_by_name

router = APIRouter(prefix="/api/friends", tags=["friends"])


class RequestIn(BaseModel):
    username: str


@router.get("")
def list_friends(me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(Friendship).where(or_(Friendship.requester_id == me.id, Friendship.addressee_id == me.id))
    ).all()
    friends, incoming, outgoing = [], [], []
    for row in rows:
        other_id = row.addressee_id if row.requester_id == me.id else row.requester_id
        other = db.get(User, other_id)
        if other is None:
            continue
        entry = {"request_id": row.id, "username": other.username}
        if row.status == "accepted":
            friends.append({**entry, **hub.presence(other.id)})
        elif row.addressee_id == me.id:
            incoming.append(entry)
        else:
            outgoing.append(entry)
    friends.sort(key=lambda f: (not f["online"], f["username"].lower()))
    return {"friends": friends, "incoming": incoming, "outgoing": outgoing}


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def send_request(body: RequestIn, me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    target = user_by_name(db, body.username)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    if target.id == me.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cant_friend_self")
    row = pair_row(db, me.id, target.id)
    if row and row.status == "accepted":
        raise HTTPException(status.HTTP_409_CONFLICT, "already_friends")
    if row and row.requester_id == me.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_requested")
    if row:
        # they already asked us, so asking back simply accepts
        row.status = "accepted"
        db.commit()
        await hub.notify(target.id, {"t": "friend_accepted", "from": me.username})
        return {"status": "accepted", "username": target.username}
    db.add(Friendship(requester_id=me.id, addressee_id=target.id))
    db.commit()
    await hub.notify(target.id, {"t": "friend_request", "from": me.username})
    return {"status": "pending", "username": target.username}


def _incoming(db: Session, me: User, request_id: int) -> Friendship:
    row = db.get(Friendship, request_id)
    if row is None or row.status != "pending" or row.addressee_id != me.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "request_not_found")
    return row


@router.post("/requests/{request_id}/accept")
async def accept(request_id: int, me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    row = _incoming(db, me, request_id)
    row.status = "accepted"
    db.commit()
    await hub.notify(row.requester_id, {"t": "friend_accepted", "from": me.username})
    return {"status": "accepted"}


@router.post("/requests/{request_id}/decline")
def decline(request_id: int, me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    db.delete(_incoming(db, me, request_id))
    db.commit()
    return {"status": "declined"}


@router.delete("/{username}")
def remove(username: str, me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Unfriend, or cancel a request you sent."""
    other = user_by_name(db, username)
    row = pair_row(db, me.id, other.id) if other else None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_friends")
    db.delete(row)
    db.commit()
    return {"status": "removed"}
