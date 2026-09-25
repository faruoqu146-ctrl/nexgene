"""NexGene bootstrap: load application core and apply production + correctness patches."""
import os
import urllib.request
import logging

_log = logging.getLogger("nexgene.bootstrap")

# Render DATABASE_URL often uses postgres://
_db = os.getenv("DATABASE_URL", "")
if _db.startswith("postgres://"):
    os.environ["DATABASE_URL"] = "postgresql://" + _db[len("postgres://"):]

# Strip accidental quotes/whitespace from OAuth client id in env UI
_gid = os.getenv("GOOGLE_CLIENT_ID", "").strip().strip('"').strip("'")
if _gid:
    os.environ["GOOGLE_CLIENT_ID"] = _gid

# Prefer local full module when present (docker / local checkout)
_local = os.path.join(os.path.dirname(__file__), "_main_full.py")
if os.path.isfile(_local):
    with open(_local, encoding="utf-8") as f:
        _code = f.read()
else:
    _URL = "https://raw.githubusercontent.com/faruoqu146-ctrl/nexgene/d38d2a8109949d06577d12ab77ed9613cb889c51/backend/app/main.py"
    _code = urllib.request.urlopen(_URL, timeout=30).read().decode("utf-8")

# --- Critical correctness patches (SQLite returns naive datetimes) ---
if "def ensure_utc(" not in _code:
    _code = _code.replace(
        "def now():\n    return datetime.now(timezone.utc)\n\n\ndef hash_token(v: str):",
        "def now():\n    return datetime.now(timezone.utc)\n\n\ndef ensure_utc(dt):\n"
        "    if dt is None:\n        return None\n"
        "    if getattr(dt, \"tzinfo\", None) is None:\n        return dt.replace(tzinfo=timezone.utc)\n"
        "    return dt.astimezone(timezone.utc)\n\n\ndef hash_token(v: str):",
    )
_code = _code.replace(
    "if not st or st.expires_at < now():",
    "if not st or ensure_utc(st.expires_at) < now():",
)
_code = _code.replace(
    'if not row or row.expires_at < now():\n        raise HTTPException(400, "Invalid or expired verification token")',
    'if not row or ensure_utc(row.expires_at) < now():\n        raise HTTPException(400, "Invalid or expired verification token")',
)
_code = _code.replace(
    'if not row or row.expires_at < now():\n        raise HTTPException(400, "Invalid or expired reset token")',
    'if not row or ensure_utc(row.expires_at) < now():\n        raise HTTPException(400, "Invalid or expired reset token")',
)
_code = _code.replace(
    "week = [r for r in rows if r.recorded_at >= start]",
    "week = [r for r in rows if ensure_utc(r.recorded_at) >= start]",
)

# Google clock skew + clearer errors
_code = _code.replace(
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID\n        )",
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID, clock_skew_in_seconds=60\n        )",
)
_code = _code.replace(
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID)",
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID, clock_skew_in_seconds=60)",
)

# Rate-limit bypass for tests
if 'if os.getenv("TESTING"' not in _code:
    _code = _code.replace(
        "def rate_limit(request: Request, key: str, limit: int, s: Session):\n",
        'def rate_limit(request: Request, key: str, limit: int, s: Session):\n'
        '    if os.getenv("TESTING", "").lower() in ("1", "true", "yes"):\n'
        '        return\n',
    )

# Valid dummy hash for timing-safe login
_code = _code.replace(
    'DUMMY_PASSWORD_HASH = "$pbkdf2-sha256$600000$9PBQ3N3VVpJN.thwvCU_MQ$DVs5WExtR1AqiTUGZRi4Mo5gcARwsRsGlq.YmryBjUM"',
    'DUMMY_PASSWORD_HASH = "$pbkdf2-sha256$600000$XetdS.md05oz5vzfm1MK4Q$63itU5/GQMODjJECGqljCF6.J3TgY5tc3GcbFSx5ltM"',
)

exec(compile(_code, "backend/app/main.py", "exec"), globals())
