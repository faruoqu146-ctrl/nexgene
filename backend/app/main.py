"""Offline self-extracting NexGene main (zlib shards)."""
from pathlib import Path
import zlib, base64
_b64 = "".join(p.read_text() for p in sorted(Path(__file__).parent.glob("_src_*.b64")))
exec(compile(zlib.decompress(base64.b64decode(_b64)), __file__, "exec"), globals())
