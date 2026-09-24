# NexGene v1.0.0

Phase 4: personalization context and the Weekly NexGene Report, building on v1.1.0 Signals and the v0.8.x security hardening.

## Run locally

```bash
docker compose up --build
```

Open **http://localhost:8000**.

## Test

```bash
docker compose exec api pytest -q
```

## v1.0.0: Personalization + Weekly Report

- Adds a lightweight personal-context profile: age range, country, occupation/work role, student status, study field, schedule and optional timezone.
- Context is used as an analysis lens, not a stereotype engine. Occupation and country do not automatically produce health conclusions.
- Adds `/api/v1/profile` with authenticated, CSRF-protected updates.
- Adds the **Weekly NexGene Report** at `/api/v1/reports/weekly`.
- Weekly reports summarize recorded signal, compare with the available personal window, identify cautious relationships, surface positive observations, and offer one small experiment for the following week.
- Reports explicitly distinguish patterns from diagnoses and avoid pretending that one week proves causation.
- The UI adds a lightweight context onboarding screen and a dedicated REPORT view.
- User/API-derived report content is rendered through safe DOM construction, not `innerHTML`.

## Security posture carried forward

- Production startup refuses weak/missing `SECRET_KEY`.
- Production startup requires `COOKIE_SECURE=true`.
- Production disables `/docs`, `/redoc`, and `/openapi.json`.
- Login uses a dummy PBKDF2 verification path for missing accounts.
- Registration uses a uniform response for existing accounts.
- Password-reset requests never expose reset tokens outside `DEV_MODE`.
- Rate limiting is persisted in the database.
- Check-in payloads are capped by request size, observation count, allow-list and text length.
- CSRF rotation updates the server-side session hash.
- Session revocation remains active on logout and password reset.
- PBKDF2-SHA256 uses 600,000 rounds.

## Development configuration

Local development intentionally keeps `DEV_MODE=true` and `COOKIE_SECURE=false` so the app can run on plain HTTP. Development-only verification/reset tokens may appear in API responses because no mail provider is configured.

**Never expose that configuration publicly.** Production must use a strong random `SECRET_KEY`, `DEV_MODE=false`, `COOKIE_SECURE=true`, HTTPS, and a managed database.

## Current scope

v1.0.0 remains a development build for lifestyle and simple physiological signals. Clinical and genetic data are not connected to this release. Those future domains require separate authorization boundaries, stronger isolation, auditability, provenance, explicit patient consent and dedicated security testing before integration.

The four NexGene data pillars remain equal in the long-term data model: lifestyle, physiological, clinical and genetic. User interaction remains lifestyle-heavy, with simple physiological entry available and hospital-driven clinical/genetic ingestion planned later.

## NexGene Signals

Signals provide gentle, data-driven reasons to return without guilt-based streak mechanics: early baseline milestones, changes in readings, emerging relationships and reasons to check in or explore Patterns.

## Weekly NexGene Report

The product cadence is now:

**Record → Discover → Get curious → Return → Discover more → Weekly report**

The report is intentionally conversational. Serious calculations stay underneath; the user-facing layer should feel like a smart friend who has been quietly paying attention, not a statistics department.


## v1.1.0 additions
- Refined account creation/sign-in experience with manual email/password and optional Google Sign-In.
- Google Sign-In is server-verified and only enabled when `GOOGLE_CLIENT_ID` is configured. Existing password accounts are not silently linked by matching email.
- Optional AI-assisted weekly reports. AI is disabled by default and requires `AI_ANALYSIS_ENABLED=true` plus `OPENAI_API_KEY`. A user must explicitly enable AI analysis before weekly evidence is sent to the configured provider.
- AI receives the bounded deterministic weekly evidence, not raw clinical/genomic data.
- Added baseline security headers.

### Optional environment
- `GOOGLE_CLIENT_ID` for Google Identity Services.
- `AI_ANALYSIS_ENABLED=false` by default.
- `OPENAI_API_KEY` server-side only. Never put this key in mobile JavaScript.
- `OPENAI_MODEL` defaults to `gpt-5.6-luna` and can be changed without code changes.

Google Sign-In follows Google's Identity Services flow and server-side ID-token verification.
