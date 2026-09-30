"""Live rooms for fishing together, plus presence and push notifications.

Every logged-in player keeps one WebSocket open to a room: their own ("at home")
or a friend's ("visiting"). The server only relays messages between the people
in a room; each player's game still runs its own fishing.

Rooms live in memory. That is fine on a single Render instance; running more
than one instance would need a shared broker such as Redis.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .config import JWT_SECRET, ROOM_SIZE
from .database import SessionLocal
from .models import User
from .security import ALGORITHM
from .social import are_friends, user_by_name

router = APIRouter()

RELAYED = {"hello", "state", "catch", "emote", "world"}
MAX_MESSAGE = 4096


@dataclass
class Member:
    ws: WebSocket
    user_id: int
    username: str
    hello: dict | None = None
    # simple rate limit: at most 40 messages per 5 seconds
    window_start: float = field(default_factory=time.monotonic)
    window_count: int = 0

    def allow(self) -> bool:
        now = time.monotonic()
        if now - self.window_start > 5:
            self.window_start, self.window_count = now, 0
        self.window_count += 1
        return self.window_count <= 40


@dataclass
class Room:
    host_id: int
    host_username: str
    members: dict[int, Member] = field(default_factory=dict)
    world: dict | None = None  # the host's last "world" message: location, clock, boat


class Hub:
    def __init__(self) -> None:
        self.rooms: dict[int, Room] = {}
        self.sockets: dict[int, set[WebSocket]] = {}
        self.where: dict[int, tuple[int, str]] = {}  # user id -> (host id, host username)

    # ---- presence
    def presence(self, user_id: int) -> dict:
        if not self.sockets.get(user_id):
            return {"online": False, "at": None}
        host_id, host_name = self.where.get(user_id, (user_id, None))
        return {"online": True, "at": "home" if host_id == user_id else host_name}

    async def notify(self, user_id: int, message: dict) -> None:
        for ws in list(self.sockets.get(user_id, ())):
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def broadcast(self, room: Room, message: dict, skip: int | None = None) -> None:
        for m in list(room.members.values()):
            if m.user_id == skip:
                continue
            try:
                await m.ws.send_json(message)
            except Exception:
                pass

    # ---- joining and leaving
    def join(self, host: User, member: Member) -> Room:
        room = self.rooms.setdefault(host.id, Room(host.id, host.username))
        room.members[member.user_id] = member
        self.sockets.setdefault(member.user_id, set()).add(member.ws)
        self.where[member.user_id] = (host.id, host.username)
        return room

    def leave(self, room: Room, member: Member) -> None:
        if room.members.get(member.user_id) is member:
            del room.members[member.user_id]
        socks = self.sockets.get(member.user_id)
        if socks:
            socks.discard(member.ws)
            if not socks:
                del self.sockets[member.user_id]
                self.where.pop(member.user_id, None)
        if not room.members:
            self.rooms.pop(room.host_id, None)


hub = Hub()


def _authenticate(token: str, host_name: str) -> tuple[User, User] | str:
    """Returns (player, host) or an error string."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return "not_logged_in"
    with SessionLocal() as db:
        user = db.get(User, user_id)
        host = user_by_name(db, host_name)
        if user is None:
            return "not_logged_in"
        if host is None:
            return "no_such_world"
        if host.id != user.id and not are_friends(db, user.id, host.id):
            return "not_friends"
        db.expunge_all()
        return user, host


@router.websocket("/ws/world/{host_name}")
async def world_socket(ws: WebSocket, host_name: str) -> None:
    await ws.accept()
    # The login token arrives as the first message, not in the URL: URLs end up
    # in access logs, and a token in a log is a key to someone's account.
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=10))
        token = first.get("token", "") if isinstance(first, dict) and first.get("t") == "auth" else ""
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        token = ""
    auth = _authenticate(str(token), host_name)
    if isinstance(auth, str):
        await ws.send_json({"t": "error", "error": auth})
        await ws.close(code=4403)
        return
    user, host = auth
    room = hub.rooms.get(host.id)
    if room and user.id not in room.members and len(room.members) >= ROOM_SIZE:
        await ws.send_json({"t": "error", "error": "room_full"})
        await ws.close(code=4409)
        return
    # the same player opening a second tab replaces their first connection
    if room and user.id in room.members:
        old = room.members[user.id]
        hub.leave(room, old)
        try:
            await old.ws.close(code=4000)
        except Exception:
            pass

    me = Member(ws, user.id, user.username)
    room = hub.join(host, me)
    await ws.send_json({
        "t": "roster",
        "host": host.username,
        "you": user.username,
        "world": room.world,
        "members": [{"username": m.username, "hello": m.hello} for m in room.members.values() if m is not me],
    })
    await hub.broadcast(room, {"t": "join", "from": user.username}, skip=user.id)
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_MESSAGE or not me.allow():
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, dict) or msg.get("t") not in RELAYED:
                continue
            if msg["t"] == "world":
                if user.id != host.id:
                    continue  # only the host decides where the world is
                room.world = msg
            if msg["t"] == "hello":
                me.hello = msg
            msg["from"] = user.username
            await hub.broadcast(room, msg, skip=user.id)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.leave(room, me)
        await hub.broadcast(room, {"t": "leave", "from": user.username})
