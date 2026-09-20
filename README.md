# NexGene v0.7.1

Authentication and runtime stabilization release.

## Run

```bash
docker compose up --build
```

Open **http://localhost:8000**. The mobile UI and API are served from the same origin.

Create an account, then sign in. Your development SQLite database is persisted in the `nexgene_data` Docker volume.

## Test

```bash
docker compose exec api pytest -q
```

## v0.7.1 fixes
- Same-origin mobile UI and API
- Sign-in and registration session restoration
- Clear authentication/network errors
- Session expiry handling
- Persistent SQLite volume for development
- Health endpoint reports 0.7.1
- Existing Today, Patterns, Timeline and check-in flows retained

This is a development build, not a production deployment.
