# Tiny Tides API

Backend for the multiplayer features of [Tiny Tides](https://agongster.github.io/fishing-sim/),
a cozy pixel-art fishing game. The game itself is a static site in
[agongster.github.io](https://github.com/agongster/agongster.github.io/tree/main/fishing-sim);
this service adds accounts, friends, visiting, gifting and fishing together.

- **Stack:** FastAPI on Render, Postgres on Neon.
- **Status:** step 1 of the plan: a health check that proves the deployment and database connection work.

## Running locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optional: leave DATABASE_URL empty to use SQLite
uvicorn app.main:app --reload
# open http://localhost:8000/api/health
```

## Deploying on Render

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Environment variables:

| Name | Value |
| --- | --- |
| `DATABASE_URL` | Neon's pooled connection string |
| `JWT_SECRET` | a long random string, used to sign login tokens from step 2 on |
| `ALLOWED_ORIGINS` | `https://agongster.github.io` (no trailing slash) |

## Secrets

No secret is in this repository. They live in Render's Environment tab in
production and in a git-ignored `.env` file locally; `.env.example` lists the
names with empty values.
