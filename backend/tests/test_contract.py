import os
os.environ.setdefault("TESTING", "1")
from pathlib import Path


def _api_source(app_dir: Path) -> str:
    p0, p1 = app_dir / "main.part0", app_dir / "main.part1"
    if p0.is_file() and p1.is_file():
        return p0.read_text() + p1.read_text()
    return (app_dir / "main.py").read_text()


def test_v140_contract():
    root = Path(__file__).parents[2]
    app_dir = root / "backend/app"
    main = (app_dir / "main.py").read_text()
    body = _api_source(app_dir)
    js = (root / "mobile/app.js").read_text()
    html = (root / "mobile/index.html").read_text()
    compose = (root / "docker-compose.yml").read_text()
    readme = (root / "README.md").read_text()

    assert "urllib.request.urlopen" not in main
    assert "githubusercontent.com" not in main
    assert 'APP_VERSION = "1.4.0"' in body
    assert 'FileResponse("mobile/index.html")' in body
    assert 'app.mount("/static"' in body
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
        assert path in body, path
    assert "/static/styles.css" in html and "/static/app.js" in html
    assert "nexgene_data" in compose
    assert "activity_level" in js and "diet_quality" in js and "nicotine" in js
    assert "innerHTML" not in js
    assert "DUMMY_PASSWORD_HASH" in body
    assert "RateLimitBucket" in body
    assert 'docs_url="/docs" if DEV_MODE else None' in body
    assert "1.4.0" in readme
    assert "clinical" in readme.lower()
    assert "NexGene" in readme
    assert "require_csrf" in body
    assert "compare_digest" in body
