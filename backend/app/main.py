"""NexGene API entrypoint — reassembles source parts shipped for GitHub size limits."""
from pathlib import Path
_parts = sorted(Path(__file__).parent.glob("_main_part*.txt"))
if not _parts:
    raise RuntimeError("Missing _main_part*.txt source shards")
_code = "".join(p.read_text(encoding="utf-8") for p in _parts)
exec(compile(_code, str(Path(__file__).resolve()), "exec"), globals())
