# NexGene backend — notes for external supervision

**Version:** 1.4.0  
**Entry point:** `backend.app.main:app` (Uvicorn / Docker / `main.py` re-export)  
**Stack:** FastAPI, SQLAlchemy 2, passlib (pbkdf2_sha256), optional Google ID token, optional OpenAI

## Design boundaries

| Concern | Behavior |
|--------|----------|
| Auth | HttpOnly session cookie + CSRF double-submit (`X-CSRF-Token`) |
| Passwords | 12+ chars, upper/lower/digit/symbol; timing-safe missing-user path |
| Production | `DEV_MODE=false` requires strong `SECRET_KEY` and `COOKIE_SECURE=true` |
| Clinical | Dual authorization (user consent + provider key). Research build uses process-local maps; `CLINICAL_DATABASE_URL` is reserved for durable integration |
| AI | Opt-in; only receives structured weekly facts — never full clinical packets |
| Evidence | Architectural registry, not a medical corpus |

## What was fixed for this review build

1. **Removed remote code loading** — previous bootstrap downloaded and `exec()`’d historical source from GitHub. The API module is now fully offline in `backend/app/main.py`.
2. **`csrf_check` → `require_csrf`** — Google link and AI settings routes no longer NameError.
3. **SQLite timezone safety** — `as_utc` / `ensure_utc` normalize naive vs aware datetimes.
4. **Valid dummy password hash** — missing-user login path does not raise inside passlib.
5. **Rate-limit bypass under `TESTING=1`** — deterministic CI.
6. **`postgres://` → `postgresql://`** — Render-compatible DSN normalization.
7. **Google token clock skew** — 60s tolerance on ID token verify.
8. **Clinical subject_ref** — stable hash over `user_id` + `SECRET_KEY` (string-safe).
9. **Provider key compare** — `secrets.compare_digest` for grant/records.

## How to verify

```bash
pip install -r backend/requirements.txt
TESTING=1 \
DATABASE_URL=sqlite:////tmp/nexgene.db \
CLINICAL_DATABASE_URL=sqlite:////tmp/nexgene_clinical.db \
CLINICAL_PROVIDER_KEY=test-provider-key \
SECRET_KEY=test-secret-key-at-least-32-characters-long \
python -m pytest backend/tests/ -v
```

Expected: **12 passed**.

```bash
docker compose up --build
curl -s http://localhost:8000/api/v1/health
```

## Explicit non-goals (honest for reviewers)

- Not a medical device; not for diagnosis or treatment decisions.
- Clinical compartment in this research build is **not** a hospital-grade system of record.
- Evidence registry is empty of real literature; schema/API only.
- Genetic data plane is out of scope for v1.4.
