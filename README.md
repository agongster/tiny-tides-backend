# Tiny Tides API

Backend for the multiplayer features of [Tiny Tides](https://agongster.github.io/fishing-sim/),
a cozy pixel-art fishing game. The game itself is a static site in
[agongster.github.io](https://github.com/agongster/agongster.github.io/tree/main/fishing-sim);
this service adds accounts, friends, visiting, gifting and fishing together.

- **Stack:** FastAPI on Render, Postgres on Neon.
- **Status:** step 2 of the plan: accounts with unique usernames, plus cloud saves.

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

Send the token as `Authorization: Bearer <token>`. Interactive docs are at `/docs`.

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
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

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
