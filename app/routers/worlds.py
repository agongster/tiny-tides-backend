"""A friend's world, as seen when visiting: read-only, and only for friends."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Save, User
from ..realtime import hub
from ..security import current_user
from ..social import are_friends, user_by_name

router = APIRouter(prefix="/api/worlds", tags=["worlds"])

# Only what a visitor needs to see (decor is the tank's props). Coins and the
# rest stay private.
PUBLIC_FIELDS = ("name", "look", "boat", "location", "clock", "aquarium", "decor", "tankLvl", "unlocked")


@router.get("/{username}")
def world(username: str, me: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    host = user_by_name(db, username)
    if host is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    if host.id != me.id and not are_friends(db, me.id, host.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_friends")
    save = db.get(Save, host.id)
    if save is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_world")
    data = save.data or {}
    return {
        "username": host.username,
        **{k: data.get(k) for k in PUBLIC_FIELDS},
        "caught": (data.get("stats") or {}).get("caught", 0),
        "species": len(data.get("dex") or {}),
        **hub.presence(host.id),
    }
