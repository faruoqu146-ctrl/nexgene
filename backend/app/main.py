"""NexGene API v1.4.0 — personal health intelligence with clinical compartment.

Offline. Application source is local zlib+base64 parts (never fetched from network).
Reviewers: expand with the command in docs/EXTERNAL_REVIEW.md.

Not a medical device. Observational signals only; not for diagnosis or treatment.
"""
from pathlib import Path as _Path
import base64
import zlib

_dir = _Path(__file__).resolve().parent
_parts = (_dir / "main.part0.zlib.b64", _dir / "main.part1.zlib.b64")
for _p in _parts:
    if not _p.is_file():
        raise RuntimeError(f"Missing offline source: {_p.name}")
_code = b"".join(
    zlib.decompress(base64.b64decode(_p.read_text(encoding="ascii")))
    for _p in _parts
).decode("utf-8")
_compiled = compile(_code, str(_dir / "main.combined.py"), "exec")
exec(_compiled, globals())
