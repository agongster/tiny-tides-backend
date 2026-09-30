import os
from pathlib import Path

os.chdir(Path(__file__).parent)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
_n = [0]


def player(coins=0, name=None):
    """Registers a fresh player with an uploaded save; returns (username, headers)."""
    _n[0] += 1
    username = name or f"p{_n[0]}_social"
    r = client.post("/api/auth/register", json={"email": f"{username}@example.com", "username": username, "password": "fishingtime"})
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    data = {"name": username.title(), "location": "lagoon", "clock": 42, "look": {"hat": "straw"}, "aquarium": [{"id": "koi"}], "bucket": [{"id": "perch"}]}
    assert client.put("/api/save", headers=h, json={"data": data, "coins": coins, "version": 0}).status_code == 200
    return username, h


def befriend(a, b):
    assert client.post("/api/friends/requests", headers=a[1], json={"username": b[0]}).status_code == 201
    req = client.get("/api/friends", headers=b[1]).json()["incoming"][0]
    assert client.post(f"/api/friends/requests/{req['request_id']}/accept", headers=b[1]).status_code == 200


def test_friend_request_flow():
    a, b = player(), player()
    r = client.post("/api/friends/requests", headers=a[1], json={"username": b[0].upper()})
    assert r.json()["status"] == "pending"
    assert client.post("/api/friends/requests", headers=a[1], json={"username": b[0]}).json()["detail"] == "already_requested"
    assert client.get("/api/friends", headers=a[1]).json()["outgoing"][0]["username"] == b[0]
    incoming = client.get("/api/friends", headers=b[1]).json()["incoming"]
    assert incoming[0]["username"] == a[0]
    # a stranger can't accept someone else's request
    c = player()
    assert client.post(f"/api/friends/requests/{incoming[0]['request_id']}/accept", headers=c[1]).status_code == 404
    client.post(f"/api/friends/requests/{incoming[0]['request_id']}/accept", headers=b[1])
    friends = client.get("/api/friends", headers=a[1]).json()["friends"]
    assert friends[0]["username"] == b[0] and friends[0]["online"] is False
    assert client.post("/api/friends/requests", headers=b[1], json={"username": a[0]}).json()["detail"] == "already_friends"
    assert client.delete(f"/api/friends/{b[0]}", headers=a[1]).status_code == 200
    assert client.get("/api/friends", headers=a[1]).json()["friends"] == []


def test_asking_back_accepts_and_bad_requests():
    a, b = player(), player()
    client.post("/api/friends/requests", headers=a[1], json={"username": b[0]})
    assert client.post("/api/friends/requests", headers=b[1], json={"username": a[0]}).json()["status"] == "accepted"
    assert client.post("/api/friends/requests", headers=a[1], json={"username": "nobody_here"}).json()["detail"] == "user_not_found"
    assert client.post("/api/friends/requests", headers=a[1], json={"username": a[0]}).json()["detail"] == "cant_friend_self"


def test_decline():
    a, b = player(), player()
    client.post("/api/friends/requests", headers=a[1], json={"username": b[0]})
    rid = client.get("/api/friends", headers=b[1]).json()["incoming"][0]["request_id"]
    assert client.post(f"/api/friends/requests/{rid}/decline", headers=b[1]).status_code == 200
    assert client.get("/api/friends", headers=a[1]).json()["outgoing"] == []


def test_worlds_are_friends_only_and_hide_private_data():
    a, b, c = player(coins=500), player(), player()
    befriend(a, b)
    w = client.get(f"/api/worlds/{a[0]}", headers=b[1])
    assert w.status_code == 200
    body = w.json()
    assert body["location"] == "lagoon" and body["aquarium"] == [{"id": "koi"}]
    assert "coins" not in body and "bucket" not in body
    assert client.get(f"/api/worlds/{a[0]}", headers=c[1]).status_code == 403


def test_gifts_move_coins_atomically():
    a, b, c = player(coins=300), player(coins=10), player()
    befriend(a, b)
    r = client.post("/api/gifts", headers=a[1], json={"to": b[0], "amount": 120, "note": "for a hat"})
    assert r.status_code == 201, r.text
    assert r.json()["coins"] == 180 and r.json()["version"] == 2
    # the sender's old version is now stale, so a stale upload can't undo the gift
    stale = client.put("/api/save", headers=a[1], json={"data": {}, "coins": 300, "version": 1})
    assert stale.status_code == 409
    assert client.post("/api/gifts", headers=a[1], json={"to": b[0], "amount": 999}).json()["detail"] == "not_enough_coins"
    assert client.post("/api/gifts", headers=a[1], json={"to": c[0], "amount": 5}).json()["detail"] == "not_friends"
    assert client.post("/api/gifts", headers=a[1], json={"to": b[0], "amount": 0}).status_code == 422
    claimed = client.post("/api/gifts/claim", headers=b[1]).json()
    assert claimed["coins"] == 130 and claimed["claimed"][0]["note"] == "for a hat"
    assert client.post("/api/gifts/claim", headers=b[1]).json()["claimed"] == []
    hist = client.get("/api/gifts", headers=a[1]).json()
    assert hist["sent"][0]["amount"] == 120 and hist["remaining_today"] == 2000 - 120


def test_gift_daily_limit():
    a, b = player(coins=4000), player()
    befriend(a, b)
    for _ in range(2):
        assert client.post("/api/gifts", headers=a[1], json={"to": b[0], "amount": 1000}).status_code == 201
    r = client.post("/api/gifts", headers=a[1], json={"to": b[0], "amount": 1})
    assert r.status_code == 429 and r.json()["detail"]["remaining"] == 0


def test_save_rejects_impossible_coin_jumps():
    a = player(coins=100)
    r = client.put("/api/save", headers=a[1], json={"data": {}, "coins": 1_000_000, "version": 1})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "coins_jump"
    assert client.put("/api/save", headers=a[1], json={"data": {}, "coins": 900, "version": 1}).status_code == 200


def test_live_room_relays_between_friends():
    host, guest, stranger = player(), player(), player()
    befriend(host, guest)
    htok = host[1]["Authorization"].split()[1]
    gtok = guest[1]["Authorization"].split()[1]
    stok = stranger[1]["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/world/{host[0]}") as hws:
        hws.send_json({"t": "auth", "token": htok})
        roster = hws.receive_json()
        assert roster["t"] == "roster" and roster["members"] == []
        hws.send_json({"t": "world", "location": "cove", "clock": 10})
        # presence shows up in the guest's friends list
        f = client.get("/api/friends", headers=guest[1]).json()["friends"][0]
        assert f["online"] is True and f["at"] == "home"
        with client.websocket_connect(f"/ws/world/{host[0]}") as gws:
            gws.send_json({"t": "auth", "token": gtok})
            groster = gws.receive_json()
            assert groster["world"]["location"] == "cove"
            assert hws.receive_json() == {"t": "join", "from": guest[0]}
            gws.send_json({"t": "state", "s": "casting", "x": 200, "y": 130})
            got = hws.receive_json()
            assert got["t"] == "state" and got["from"] == guest[0] and got["x"] == 200
            # guests can't move the world, and unknown message types are dropped
            gws.send_json({"t": "world", "location": "bay"})
            gws.send_json({"t": "hack"})
            gws.send_json({"t": "emote", "e": "heart"})
            assert hws.receive_json()["t"] == "emote"
        assert hws.receive_json() == {"t": "leave", "from": guest[0]}
    # strangers are turned away
    with client.websocket_connect(f"/ws/world/{host[0]}") as sws:
        sws.send_json({"t": "auth", "token": stok})
        assert sws.receive_json() == {"t": "error", "error": "not_friends"}
        with pytest.raises(WebSocketDisconnect):
            sws.receive_json()


def test_gift_notifies_an_online_recipient():
    a, b = player(coins=50), player()
    befriend(a, b)
    btok = b[1]["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/world/{b[0]}") as ws:
        ws.send_json({"t": "auth", "token": btok})
        ws.receive_json()  # roster
        client.post("/api/gifts", headers=a[1], json={"to": b[0], "amount": 7})
        assert ws.receive_json() == {"t": "gift", "from": a[0], "amount": 7}


def test_room_rejects_missing_or_bad_auth():
    host = player()
    with client.websocket_connect(f"/ws/world/{host[0]}") as ws:
        ws.send_json({"t": "state"})  # not an auth message
        assert ws.receive_json() == {"t": "error", "error": "not_logged_in"}
    with client.websocket_connect(f"/ws/world/{host[0]}") as ws:
        ws.send_json({"t": "auth", "token": "forged"})
        assert ws.receive_json() == {"t": "error", "error": "not_logged_in"}
