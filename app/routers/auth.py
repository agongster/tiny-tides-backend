"""Sign up, log in, who am I, and username availability."""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AuthOut, LoginIn, RegisterIn, UserOut
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, email=user.email)


@router.post("/auth/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> AuthOut:
    email = body.email.lower()
    key = body.username.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "email_taken")
    if db.scalar(select(User).where(User.username_key == key)):
        raise HTTPException(status.HTTP_409_CONFLICT, "username_taken")
    user = User(email=email, username=body.username, username_key=key, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # two sign-ups raced for the same name or email
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "username_taken")
    db.refresh(user)
    return AuthOut(token=create_token(user.id), user=user_out(user))


@router.post("/auth/login", response_model=AuthOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> AuthOut:
    ident = body.login.strip().lower()
    column = User.email if "@" in ident else User.username_key
    user = db.scalar(select(User).where(column == ident))
    # same message either way, so the form can't be used to find accounts
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong_login")
    return AuthOut(token=create_token(user.id), user=user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return user_out(user)


@router.get("/usernames/{name}")
def username_available(name: str, db: Session = Depends(get_db)) -> dict:
    if not USERNAME_RE.match(name):
        return {"valid": False, "available": False}
    taken = db.scalar(select(User.id).where(User.username_key == name.lower())) is not None
    return {"valid": True, "available": not taken}
