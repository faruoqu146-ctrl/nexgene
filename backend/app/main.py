"""Bootstrap: load complete main from last known good commit on GitHub.

Requires network at first import. Full offline main.py is in commit d38d2a8.
Normalizes Render DATABASE_URL (postgres:// -> postgresql://) before import.
"""
import os
import urllib.request

# Render often provides postgres://; SQLAlchemy expects postgresql://
_db = os.getenv("DATABASE_URL", "")
if _db.startswith("postgres://"):
    os.environ["DATABASE_URL"] = "postgresql://" + _db[len("postgres://"):]

_URL = "https://raw.githubusercontent.com/faruoqu146-ctrl/nexgene/d38d2a8109949d06577d12ab77ed9613cb889c51/backend/app/main.py"
_code = urllib.request.urlopen(_URL, timeout=30).read().decode("utf-8")
exec(compile(_code, "backend/app/main.py", "exec"), globals())
