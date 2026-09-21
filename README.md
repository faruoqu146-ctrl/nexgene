# NexGene v0.8.0

Security hardening release built on v0.7.1.

## Run

```bash
docker compose up --build
```

Open **http://localhost:8000**.

## Test

```bash
docker compose exec api pytest -q
```

## Security changes

- HttpOnly, SameSite session cookies instead of localStorage bearer tokens
- CSRF protection for authenticated state-changing requests
- Argon2 password hashing
- Password policy: 12+ chars, upper, lower, number, symbol
- Login, registration and reset rate limiting
- Session revocation on logout and password reset
- Single-use expiring email-verification tokens
- Single-use expiring password-reset tokens
- Account enumeration reduced for registration and password-reset request responses
- Same-origin API/UI with permissive CORS removed
- Production configuration knobs for SECRET_KEY and secure cookies
- Development-only verification/reset tokens are returned in API responses while no mail provider is configured

## Important

This is still a development build. `DEV_MODE=true` is intentionally convenient for local testing and MUST be disabled in a real deployment. Production should use HTTPS and `COOKIE_SECURE=true`, a strong secret, a real email delivery provider, a managed database, centralized rate limiting, security monitoring and a proper backup/recovery process.

The four NexGene data pillars remain equal in the data model roadmap: lifestyle, physiological, clinical and genetic. User interaction remains lifestyle-heavy, with simple physiological entry available and hospital-driven clinical/genetic ingestion planned for later phases.
