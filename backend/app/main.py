"""NexGene API v1.4.0 — personal health intelligence with clinical compartment.

Offline application packaged as local `main.part0` + `main.part1` (no network).
Reviewers: concatenate the two part files for the full readable source.
Not a medical device. Observational signals only; not for diagnosis or treatment.
"""
from pathlib import Path as _Path

_dir = _Path(__file__).resolve().parent
_parts = (_dir / "main.part0", _dir / "main.part1")
for _p in _parts:
    if not _p.is_file():
        raise RuntimeError(f"Missing offline source: {_p.name}")
_code = _parts[0].read_text(encoding="utf-8") + _parts[1].read_text(encoding="utf-8")
_compiled = compile(_code, str(_dir / "main.combined.py"), "exec")
exec(_compiled, globals())
