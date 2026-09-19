# NexGene v0.7.0

## Phase: Patterns & Longitudinal Intelligence

This iteration moves NexGene from a check-in prototype toward a product that learns from the user's history.

### Included
- Raven-inspired visual system
- Account creation and sign-in UI
- Tap-first morning/evening check-ins
- Expanded lifestyle variables
- Today snapshot
- 30-day Patterns view with daily trend visualization
- Living Timeline view
- Early longitudinal insights API
- Server-side user identity enforcement
- Dockerized FastAPI + SQLite development stack
- Contract test
- Mobile frontend served from the API root (`/`)

## Run

### With Docker
```bash
docker compose up --build
```

Open http://localhost:8000

API docs: http://localhost:8000/docs

Tests:
```bash
docker compose exec api pytest -q
```

### Local (no Docker)
```bash
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000

```bash
pytest backend/tests -q
```

## Important
This is still a development prototype. It is not production-ready for clinical or research deployment. The next engineering hardening layer should restore PostgreSQL as the default service, add migrations, structured provenance/consent, exports/deletion, rate limiting, and stronger auth/session controls.
