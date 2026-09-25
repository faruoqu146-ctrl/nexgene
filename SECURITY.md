# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.4.x   | Yes       |

## Reporting a vulnerability

Please report security issues privately. Do not open public GitHub issues for vulnerabilities that could expose user health data or session tokens.

## Design principles

- Session cookies are HttpOnly; CSRF tokens are double-submit with server-side hash verification.
- Production refuses weak `SECRET_KEY` and insecure cookies (`DEV_MODE=false`).
- Clinical data lives in a separate database with dual authorization (user consent + provider grant) and immediate revocation.
- Biomarker and observation writes are authenticated, CSRF-protected, and user-scoped.
- AI analysis is opt-in and receives only structured, bounded packets — never unrestricted history.
- Rate limiting applies to auth and sensitive endpoints.
- Request body size is capped.

## Development secrets

Never commit real provider keys, `SECRET_KEY` values, or production database credentials. Use `.env` (gitignored) and rotate any key that may have been exposed.
