# NexGene v1.4.0

**Personal health intelligence with a dual-authorized clinical compartment.**

NexGene is a privacy-first API and mobile web client for longitudinal lifestyle and physiological signals, molecular/biomarker deviation tracking, evidence-linked insights, and a strictly isolated clinical data plane.

Built for correctness under incomplete data, explicit uncertainty, and clear boundaries between observation, inference, and clinical escalation.

---

## Why this architecture

| Pillar | Role |
|--------|------|
| **Lifestyle** | Self-reported check-ins (sleep, energy, stress, activity, …) |
| **Physiological** | Sensor-style and quantitative trends |
| **Molecular / biomarker** | Lab values *or* direction/significance deviation signals |
| **Clinical** | Separate store; dual auth; never mixed into the consumer timeline by default |
| **Genetic** | Reserved (out of scope for v1.4) |

Clinical records require **user consent + provider authorization**. Revocation immediately removes application access. The intelligence brief may expose only a **bounded** clinical context when dual authorization exists — never the full clinical packet to the optional AI layer.

---

## Quick start

```bash
cp .env.example .env   # edit secrets for anything beyond local demo
docker compose up --build
```

| Surface | URL |
|---------|-----|
| API | http://localhost:8000 |
| Health | http://localhost:8000/api/v1/health |
| Mobile UI | http://localhost:8000/ |
| OpenAPI | http://localhost:8000/docs *(only when `DEV_MODE=true`)* |

### Local tests (no Docker)

```bash
pip install -r backend/requirements.txt
TESTING=1 \
DATABASE_URL=sqlite:////tmp/nexgene.db \
CLINICAL_DATABASE_URL=sqlite:////tmp/nexgene_clinical.db \
CLINICAL_PROVIDER_KEY=test-provider-key \
python -m pytest backend/tests/ -v
```

---

## Security boundaries (non-negotiable)

- **Auth**: cookie sessions + CSRF double-submit; password policy enforced; timing-safe login path with dummy hash verification.
- **Production gates**: `DEV_MODE=false` requires a strong `SECRET_KEY` (≥32 chars) and `COOKIE_SECURE=true`.
- **Clinical plane**: separate `CLINICAL_DATABASE_URL`; opaque `subject_ref`; provider sync behind `X-Clinical-Provider-Key` in development builds.
- **Data minimization for AI**: structured weekly report + intelligence brief only; diagnosis/treatment language is disallowed by design.
- **Rate limits** on register/login/reset and related endpoints.
- **Headers**: `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`.

See [SECURITY.md](SECURITY.md).

---

## API surface (v1)

| Area | Endpoints (representative) |
|------|----------------------------|
| Auth | `/api/v1/auth/register`, `login`, `logout`, `csrf`, `me`, password reset |
| Profile | `/api/v1/profile` |
| Check-ins | `/api/v1/checkins/morning` (and related) |
| Reports | `/api/v1/reports/weekly` |
| Biomarkers | `/api/v1/biomarkers`, `/api/v1/biomarkers/signals` |
| Intelligence | `/api/v1/intelligence/brief`, `insights`, `data-quality` |
| Evidence | `/api/v1/evidence/search`, `import` *(dev-only)* |
| Clinical | `/api/v1/clinical/consent`, `revoke`, `records`; provider `grant` / `records` |

`APP_VERSION = 1.4.0`

---

## Clinical compartment (Phase 7)

```bash
CLINICAL_DATABASE_URL=sqlite:///./nexgene_clinical.db
CLINICAL_PROVIDER_ID=development-provider
CLINICAL_PROVIDER_KEY=replace-with-a-local-development-secret
```

1. User consents → opaque `subject_ref` issued.  
2. Provider grants authorization with the provider key.  
3. Provider may sync records only when consent exists.  
4. User revocation clears application access immediately.

**Do not** expose development provider keys. Production hospital integration must replace the shared key with organization-grade identity, mutual TLS, and audit logging.

---

## Development notes

- Evidence registry is an **architectural foundation**, not a populated medical corpus.
- Associations from the personal baseline / multi-factor engine are **explicitly non-causal**.
- Sparse data surfaces coverage and quality so the product does not pretend certainty.

Further design detail: `docs/PHASE_5_ARCHITECTURE.md`, `docs/PHASE_6_PERSONAL_HEALTH_INTELLIGENCE.md`, `docs/PHASE_7_CLINICAL_COMPARTMENT.md`.

---

## License & status

Research / development build. Not a medical device. Not for diagnosis or treatment decisions.
