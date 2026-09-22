# NexGene v0.8.1

APP_VERSION 0.8.1 — Security hardening follow-up to v0.8.0, based directly on the 21 September 2026 adversarial assessment.

## Run locally

```bash
docker compose up --build
```

Open **http://localhost:8000**.

## Test

```bash
docker compose exec api pytest -q
```

## Security changes in v0.8.1

- Production startup refuses weak/missing `SECRET_KEY`.
- Production startup requires `COOKIE_SECURE=true`.
- Production disables `/docs`, `/redoc`, and `/openapi.json`.
- Login uses a dummy PBKDF2 verification path for missing accounts to reduce timing-based account enumeration.
- Registration uses a uniform response for existing accounts.
- Password-reset requests never expose reset tokens outside `DEV_MODE`.
- Rate limiting is persisted in the database instead of process-local memory, allowing shared limits across application instances using the same database.
- Check-in payloads are capped by request size, number of observations, allowed observation kinds, and text value length.
- Rich UI rendering no longer inserts user/API-derived values through `innerHTML`; DOM nodes and `textContent` are used instead.
- CSRF rotation now updates the server-side session hash as well as the readable CSRF cookie.
- README now accurately documents PBKDF2-SHA256 at 600,000 rounds.

## Development configuration

Local development intentionally keeps `DEV_MODE=true` and `COOKIE_SECURE=false` so the app can run on plain HTTP. Development-only verification/reset tokens may appear in API responses because no mail provider is configured.

**Never expose that configuration publicly.** Production must use a strong random `SECRET_KEY`, `DEV_MODE=false`, `COOKIE_SECURE=true`, HTTPS, and a managed database. The database-backed rate limiter is shared when instances use the same database.

## Current scope

v0.8.1 remains a development build for lifestyle and simple physiological signals. Clinical and genetic data are not connected to this release. Those future data domains will require separate authorization boundaries, stronger isolation, auditability, provenance, and explicit patient consent before integration.

The four NexGene data pillars remain equal in the data model roadmap: lifestyle, physiological, clinical and genetic. User interaction remains lifestyle-heavy, with simple physiological entry available and hospital-driven clinical/genetic ingestion planned for later.
