"""Bootstrap: load NexGene main + production auth fixes for Render/Google."""
import os
import urllib.request

# Render DATABASE_URL often uses postgres://
_db = os.getenv("DATABASE_URL", "")
if _db.startswith("postgres://"):
    os.environ["DATABASE_URL"] = "postgresql://" + _db[len("postgres://"):]

# Strip accidental quotes/whitespace from OAuth client id in Render env UI
_gid = os.getenv("GOOGLE_CLIENT_ID", "").strip().strip('"').strip("'")
if _gid:
    os.environ["GOOGLE_CLIENT_ID"] = _gid

_URL = "https://raw.githubusercontent.com/faruoqu146-ctrl/nexgene/d38d2a8109949d06577d12ab77ed9613cb889c51/backend/app/main.py"
_code = urllib.request.urlopen(_URL, timeout=30).read().decode("utf-8")

# Allow small clock skew on free-tier hosts; surface real verify errors in logs
_code = _code.replace(
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID\n        )",
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID, clock_skew_in_seconds=60\n        )",
)
_code = _code.replace(
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID)",
    "x.credential, google_requests.Request(), GOOGLE_CLIENT_ID, clock_skew_in_seconds=60)",
)
_code = _code.replace(
    """    except Exception:\n        raise HTTPException(status_code=401, detail=\"Could not authenticate with Google\")\n    google_sub = info.get(\"sub\")\n    email = str(info.get(\"email\", \"\")).strip().lower()\n    email_verified = bool(info.get(\"email_verified\"))\n    if not google_sub or not email or not email_verified:\n        raise HTTPException(status_code=401, detail=\"Could not authenticate with Google\")\n""",
    """    except Exception as e:\n        import logging\n        logging.getLogger(\"nexgene.auth\").warning(\"Google token verify failed: %s\", e)\n        raise HTTPException(status_code=401, detail=\"Could not authenticate with Google\")\n    google_sub = info.get(\"sub\")\n    email = str(info.get(\"email\", \"\")).strip().lower()\n    email_verified = bool(info.get(\"email_verified\"))\n    if not google_sub or not email or not email_verified:\n        raise HTTPException(status_code=401, detail=\"Google account is missing a verified email\")\n""",
)

exec(compile(_code, "backend/app/main.py", "exec"), globals())
