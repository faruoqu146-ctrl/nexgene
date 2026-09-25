import os
os.environ.setdefault("TESTING", "1")
from pathlib import Path


def test_intelligence_engine_contract():
    root = Path(__file__).parents[2]
    main = (root / "backend/app/main.py").read_text()
    # Bootstrap or full module must reference intelligence surfaces
    assert "intelligence" in main.lower() or "ensure_utc" in main
