# Tiny Tides API

Backend for the multiplayer features of [Tiny Tides](https://agongster.github.io/fishing-sim/),
a cozy pixel-art fishing game. The game itself is a static site in
[agongster.github.io](https://github.com/agongster/agongster.github.io/tree/main/fishing-sim);
this service adds accounts, friends, visiting, gifting and fishing together.

- **Stack:** FastAPI on Render, Postgres on Neon.
- **Features:** accounts with unique usernames, cloud saves, friends, visiting friends' worlds, gifting coins, and live rooms for fishing together.

## API

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/health` | Is the API up, and can it reach the database? |
| POST | `/api/auth/register` | `{email, username, password}` → `{token, user}`. Usernames are 3–16 letters, numbers or `_`, unique regardless of capitals. |
| POST | `/api/auth/login` | `{login, password}`, where login is an email or a username → `{token, user}` |
| GET | `/api/me` | The logged-in player |
| GET | `/api/usernames/{name}` | `{valid, available}`, for live checking on the sign-up form |
| GET | `/api/save` | This player's cloud save (`exists: false` if none yet) |
| PUT | `/api/save` | `{data, coins, version}`. `version` must match the stored one, otherwise it's a 409 so a stale tab can't overwrite newer progress. |

| GET | `/api/friends` | Friends (with online status and where they are), incoming and outgoing requests |
| POST | `/api/friends/requests` | `{username}`: send a request. If they already asked you, this accepts. |
| POST | `/api/friends/requests/{id}/accept` or `/decline` | Answer a request |
| DELETE | `/api/friends/{username}` | Unfriend, or cancel a request you sent |
| GET | `/api/worlds/{username}` | A friend's world for visiting: look, boat, location, clock, aquarium. No coins or bucket. |
| POST | `/api/gifts` | `{to, amount, note}`: send coins to a friend (1–1000 each, 2000 a day) |
| GET | `/api/gifts` | Recent gifts sent and received |
| POST | `/api/gifts/claim` | Collect waiting gifts into your balance |
| WS | `/ws/world/{host}` | Live room in `host`'s world (the host or their friends, 4 people max). The first message must be `{"t": "auth", "token": …}`. |

Send the token as `Authorization: Bearer <token>`. A WebSocket can't carry that header from a browser, so it sends the token as its first message instead of in the URL, which would put it in the access logs. Interactive docs are at `/docs`.

## How the multiplayer parts work

- **Gifts:** coins only move inside the database, with one conditional UPDATE (`coins >= amount`), so nobody can overspend even by sending two gifts at once. Every server-side coin change bumps the save's version, so a game that hadn't heard about it gets a 409 instead of overwriting the new balance. Gifts wait in a mailbox until the recipient claims them, and an online recipient is pinged over their WebSocket.
- **Cheating:** the game runs in the browser, so it can't be made cheat-proof. The server refuses uploads whose coins jump by more than real fishing could earn (5000 plus 300 per second since the last upload). Combined with the daily gift cap, this limits how far edited coins can spread.
- **Live rooms:** every logged-in player keeps one WebSocket open, to their own world or a friend's. The server relays casts, catches, emotes and (from the host only) the world's location and time; each player's game still runs its own fishing. Messages are size-limited and rate-limited. Rooms live in memory, which is fine for one Render instance; more than one would need a shared broker like Redis.

## Running locally

Use Python 3.11 (what Render runs; the pinned libraries need 3.10+).

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # optional: leave DATABASE_URL empty to use SQLite
uvicorn app.main:app --reload
# open http://localhost:8000/docs
pytest          # runs the API tests against a throwaway SQLite database
```

## Deploying on Render

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`

  Keep `--workers 1`. Live rooms and online status live in memory, so every
  player has to reach the same process. Without the flag, uvicorn starts one
  process per `WEB_CONCURRENCY`, and friends end up in different copies of the
  server: visitors see the host as napping and nobody sees anyone. `/api/health`
  shows `"process"`, which should stay the same across refreshes.

Environment variables:

| Name | Value |
| --- | --- |
| `DATABASE_URL` | Neon's pooled connection string |
| `JWT_SECRET` | a long random string that signs login tokens. The server refuses to start without it when using a real database. |
| `ALLOWED_ORIGINS` | `https://agongster.github.io` (no trailing slash) |

## Secrets

Passwords are hashed with bcrypt and never stored or logged in plain text. No secret is in this repository. They live in Render's Environment tab in
production and in a git-ignored `.env` file locally; `.env.example` lists the
names with empty values.
