import os
os.environ.setdefault("TESTING", "1")
from pathlib import Path


def test_v140_contract():
    root = Path(__file__).parents[2]
    main = (root / "backend/app/main.py").read_text()
    js = (root / "mobile/app.js").read_text()
    html = (root / "mobile/index.html").read_text()
    compose = (root / "docker-compose.yml").read_text()
    readme = (root / "README.md").read_text()

    assert 'APP_VERSION = "1.4.0"' in main
    assert 'FileResponse("mobile/index.html")' in main
    assert 'app.mount("/static"' in main
    assert "window.location.origin" in js
    assert "/api/v1/auth/login" in js and "/api/v1/auth/register" in js
    assert "/api/v1/auth/me" in js
    for path in (
        "/api/v1/patterns",
        "/api/v1/insights",
        "/api/v1/signals",
        "/api/v1/profile",
        "/api/v1/reports/weekly",
        "/api/v1/biomarkers/signals",
        "/api/v1/intelligence/brief",
        "/api/v1/evidence/search",
        "/api/v1/intelligence/insights",
        "/api/v1/intelligence/data-quality",
        "/api/v1/clinical/consent",
    ):
        assert path in main, path
    assert "/static/styles.css" in html and "/static/app.js" in html
    assert "nexgene_data" in compose
    assert "activity_level" in js and "diet_quality" in js and "nicotine" in js
    assert "innerHTML" not in js
    assert "DUMMY_PASSWORD_HASH" in main
    assert "RateLimitBucket" in main
    assert 'docs_url="/docs" if DEV_MODE else None' in main
    assert "1.4.0" in readme
    assert "clinical" in readme.lower()
    assert "NexGene" in readme
