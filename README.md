# NexGene v0.7.0

Patterns & Longitudinal Intelligence — mobile-first wellness check-ins with FastAPI.

## Run locally

```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

## Deploy on Vercel

This repo is configured for Vercel’s Python / FastAPI runtime:

- Entrypoint: `backend.app.main:app` (see `pyproject.toml`)
- Static UI: `public/` (served by Vercel CDN)
- Default DB: SQLite in `/tmp` (ephemeral — demo only)

For persistent data, set `DATABASE_URL` to a Postgres connection string (e.g. Neon free tier) and `SECRET_KEY` in Vercel env vars.

```bash
vercel          # preview
vercel --prod   # production
```

Or import the GitHub repo at https://vercel.com/new

## Docker

```bash
docker compose up --build
```

## Tests

```bash
pytest backend/tests -q
```

## Note

Prototype only — not for clinical use. Next: Postgres, migrations, stronger auth.
