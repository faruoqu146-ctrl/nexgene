"""Runtime configuration for NexGene."""
from __future__ import annotations

import os

# Render / Heroku often provide postgres:// — SQLAlchemy expects postgresql://
_db = os.getenv("DATABASE_URL", "")
if _db.startswith("postgres://"):
    os.environ["DATABASE_URL"] = "postgresql://" + _db[len("postgres://") :]

_gid = os.getenv("GOOGLE_CLIENT_ID", "").strip().strip('"').strip("'")
if _gid:
    os.environ["GOOGLE_CLIENT_ID"] = _gid

APP_VERSION = "1.4.0"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nexgene.db")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = 7
RATE_WINDOW = 60
MAX_LOGIN_ATTEMPTS = 5 if not DEV_MODE else 200
MAX_REGISTER_ATTEMPTS = 10 if not DEV_MODE else 200
MAX_RESET_ATTEMPTS = 5 if not DEV_MODE else 200
MAX_VERIFY_ATTEMPTS = 10 if not DEV_MODE else 200
MAX_CHECKIN_KEYS = 16
MAX_VALUE_LENGTH = 256
MAX_REQUEST_BYTES = 16 * 1024
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
AI_ANALYSIS_ENABLED = os.getenv("AI_ANALYSIS_ENABLED", "false").lower() == "true"
CLINICAL_DATABASE_URL = os.getenv("CLINICAL_DATABASE_URL", "sqlite:///./nexgene_clinical.db")
CLINICAL_PROVIDER_ID = os.getenv("CLINICAL_PROVIDER_ID", "development-provider")
CLINICAL_PROVIDER_KEY = os.getenv("CLINICAL_PROVIDER_KEY", "")

if not DEV_MODE:
    if not SECRET_KEY or len(SECRET_KEY) < 32 or SECRET_KEY == "nexgene-dev-secret-change-me":
        raise RuntimeError(
            "SECRET_KEY must be a strong random value of at least 32 characters when DEV_MODE=false"
        )
    if not COOKIE_SECURE:
        raise RuntimeError("COOKIE_SECURE=true is required when DEV_MODE=false")
elif not SECRET_KEY:
    SECRET_KEY = "nexgene-local-development-secret-only"

# Valid pbkdf2-sha256 hash so passlib.verify does not raise on missing-user login path
DUMMY_PASSWORD_HASH = (
    "$pbkdf2-sha256$600000$XetdS.md05oz5vzfm1MK4Q$63itU5/GQMODjJECGqljCF6.J3TgY5tc3GcbFSx5ltM"
)
