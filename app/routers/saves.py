"""The player's cloud save: one JSON document plus a coin balance."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from ..config import COIN_JUMP_BASE, COIN_RATE, MAX_SAVE_BYTES
from ..database import get_db
from ..models import Save, User
from ..schemas import SaveIn, SaveOut
from ..security import current_user
from ..social import as_utc

router = APIRouter(prefix="/api/save", tags=["save"])


def save_out(s: Save | None) -> SaveOut:
    if s is None:
        return SaveOut(exists=False)
    return SaveOut(exists=True, data=s.data, coins=s.coins, version=s.version, updated_at=s.updated_at)


@router.get("", response_model=SaveOut)
def get_save(user: User = Depends(current_user), db: Session = Depends(get_db)) -> SaveOut:
    return save_out(db.get(Save, user.id))


@router.put("", response_model=SaveOut)
def put_save(body: SaveIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> SaveOut:
    if len(json.dumps(body.data)) > MAX_SAVE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "save_too_large")
    current = db.get(Save, user.id)
    current_version = current.version if current else 0
    if body.version != current_version:
        # someone (another tab or device) saved since this client last synced
        raise HTTPException(status.HTTP_409_CONFLICT, {"error": "version_conflict", "current_version": current_version})
    if current is not None and body.coins > current.coins:
        elapsed = (datetime.now(timezone.utc) - as_utc(current.updated_at)).total_seconds()
        if body.coins - current.coins > COIN_JUMP_BASE + COIN_RATE * max(0, elapsed):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"error": "coins_jump", "coins": current.coins})
    # coins are also kept in the column; the copy inside data is ignored by the game
    data = {k: v for k, v in body.data.items() if k != "coins"}
    if current is None:
        current = Save(user_id=user.id, data=data, coins=body.coins, version=1)
        db.add(current)
    else:
        current.data = data
        current.coins = body.coins
        current.version = current_version + 1
    db.commit()
    db.refresh(current)
    return save_out(current)
