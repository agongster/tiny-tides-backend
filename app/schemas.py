"""Request and response shapes."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints

Username = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]{3,16}$")]


class RegisterIn(BaseModel):
    email: EmailStr
    username: Username
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=254, description="email or username")
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    email: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


class SaveIn(BaseModel):
    data: dict
    coins: int = Field(ge=0)
    version: int = Field(ge=0, description="the version this save was based on")


class SaveOut(BaseModel):
    exists: bool
    data: dict | None = None
    coins: int = 0
    version: int = 0
    updated_at: datetime | None = None
