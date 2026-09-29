import os
from pathlib import Path

os.chdir(Path(__file__).parent)  # the SQLite fallback file lands in tests/

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def register(username="April", email="april@example.com", password="fishingtime"):
    return client.post("/api/auth/register", json={"email": email, "username": username, "password": password})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_register_login_me():
    r = register()
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    assert client.get("/api/me", headers=auth(token)).json()["username"] == "April"
    # log in by username (any case) or by email
    assert client.post("/api/auth/login", json={"login": "april", "password": "fishingtime"}).status_code == 200
    assert client.post("/api/auth/login", json={"login": "APRIL@example.com", "password": "fishingtime"}).status_code == 200
    bad = client.post("/api/auth/login", json={"login": "april", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["detail"] == "wrong_login"


def test_usernames_are_unique_case_insensitively():
    register(username="Bobbo", email="bob@example.com")
    r = register(username="bobbo", email="bob2@example.com")
    assert r.status_code == 409 and r.json()["detail"] == "username_taken"
    assert client.get("/api/usernames/BOBBO").json() == {"valid": True, "available": False}
    assert client.get("/api/usernames/fresh_name").json() == {"valid": True, "available": True}
    assert client.get("/api/usernames/no spaces!").json()["valid"] is False


def test_duplicate_email_and_bad_input():
    register(username="Cleo", email="cleo@example.com")
    assert register(username="Cleo2", email="CLEO@example.com").json()["detail"] == "email_taken"
    assert register(username="ab", email="short@example.com").status_code == 422
    assert register(username="Dora", email="dora@example.com", password="short").status_code == 422


def test_save_roundtrip_and_version_conflict():
    token = register(username="Eve", email="eve@example.com").json()["token"]
    h = auth(token)
    assert client.get("/api/save", headers=h).json()["exists"] is False
    r = client.put("/api/save", headers=h, json={"data": {"name": "Eve", "coins": 999}, "coins": 12, "version": 0})
    assert r.status_code == 200 and r.json()["version"] == 1 and r.json()["coins"] == 12
    assert "coins" not in r.json()["data"]
    # a stale client (still on version 0) is refused
    stale = client.put("/api/save", headers=h, json={"data": {}, "coins": 0, "version": 0})
    assert stale.status_code == 409 and stale.json()["detail"]["current_version"] == 1
    ok = client.put("/api/save", headers=h, json={"data": {"name": "Eve"}, "coins": 30, "version": 1})
    assert ok.json()["version"] == 2


def test_save_requires_login_and_rejects_negative_coins():
    assert client.get("/api/save").status_code == 401
    assert client.get("/api/save", headers=auth("garbage")).status_code == 401
    token = register(username="Finn", email="finn@example.com").json()["token"]
    r = client.put("/api/save", headers=auth(token), json={"data": {}, "coins": -5, "version": 0})
    assert r.status_code == 422


def test_cors_allows_the_game_only():
    ok = client.options("/api/save", headers={"Origin": "https://agongster.github.io", "Access-Control-Request-Method": "PUT"})
    assert ok.headers.get("access-control-allow-origin") == "https://agongster.github.io"
    bad = client.options("/api/save", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "PUT"})
    assert "access-control-allow-origin" not in bad.headers
