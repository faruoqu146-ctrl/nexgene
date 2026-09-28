"""NexGene bootstrap: offline-first load + production auth patches."""
import os
import urllib.request
import logging

_log = logging.getLogger("nexgene.bootstrap")

_db = os.getenv("DATABASE_URL", "")
if _db.startswith("postgres://"):
    os.environ["DATABASE_URL"] = "postgresql://" + _db[len("postgres://"):]

_gid = os.getenv("GOOGLE_CLIENT_ID", "").strip().strip('"').strip("'")
if _gid:
    os.environ["GOOGLE_CLIENT_ID"] = _gid

_local = os.path.join(os.path.dirname(__file__), "_main_full.py")
if os.path.isfile(_local):
    with open(_local, encoding="utf-8") as f:
        _code = f.read()
else:
    _URL = (
        "https://raw.githubusercontent.com/faruoqu146-ctrl/nexgene/"
        "d38d2a8109949d06577d12ab77ed9613cb889c51/backend/app/main.py"
    )
    _code = urllib.request.urlopen(_URL, timeout=30).read().decode("utf-8")

_code = _code.replace("csrf_check(", "require_csrf(")
_code = _code.replace(
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID)",
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID, clock_skew_in_seconds=60)",
)
_code = _code.replace(
    'DUMMY_PASSWORD_HASH = "$pbkdf2-sha256$600000$CQGAsLY2hrBWKkWIEeI8Jw$sQ9YMNiB3hPTZcz7rPO8.b/ipifzjeXnmnrN7oN/KA4"',
    'DUMMY_PASSWORD_HASH = "$pbkdf2-sha256$600000$FMI4ZwzhXCsFgJByDgEgpA$1bcAR/yIQ6NygmQqYc6GEqL03OrGQXzepR2Zjnc5ExI"',
)

# Disable rate_limit writes (were crashing auth when RateLimitBucket schema mismatched)
_code = _code.replace(
    "def rate_limit(request: Request, key: str, limit: int, s: Session):\n    ip = request.client.host if request.client else \"unknown\"",
    "def rate_limit(request: Request, key: str, limit: int, s: Session):\n    return\n    ip = request.client.host if request.client else \"unknown\"",
)

_code = _code.replace(
    "if not pwd.verify(x.password, u.password_hash):\n        raise HTTPException(401, \"Invalid email or password\")",
    "try:\n        _ok = pwd.verify(x.password, u.password_hash)\n    except Exception:\n        _ok = False\n    if not _ok:\n        raise HTTPException(401, \"Invalid email or password\")",
)
_code = _code.replace(
    "pwd.verify(x.password, DUMMY_PASSWORD_HASH)\n        raise HTTPException(401, \"Invalid email or password\")",
    "try:\n            pwd.verify(x.password, DUMMY_PASSWORD_HASH)\n        except Exception:\n            pass\n        raise HTTPException(401, \"Invalid email or password\")",
)

exec(compile(_code, "backend/app/main.py", "exec"), globals())

# --- Schema repair for Postgres (create_all does not ALTER existing tables) ---
try:
    from sqlalchemy import inspect, text as _sql_text

    _insp = inspect(engine)
    _tables = set(_insp.get_table_names())
    if "users" in _tables:
        _cols = {c["name"] for c in _insp.get_columns("users")}
        with engine.begin() as _conn:
            if "email_verified" not in _cols:
                _conn.execute(_sql_text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE"))
            if "google_sub" not in _cols:
                _conn.execute(_sql_text("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)"))
            if "ai_analysis_enabled" not in _cols:
                _conn.execute(_sql_text("ALTER TABLE users ADD COLUMN ai_analysis_enabled BOOLEAN DEFAULT FALSE"))
    # Ensure all model tables exist (including rate_limit_buckets)
    Base.metadata.create_all(engine)
    _log.info("nexgene schema repair complete")
except Exception as _e:
    _log.exception("nexgene schema repair failed: %s", _e)
