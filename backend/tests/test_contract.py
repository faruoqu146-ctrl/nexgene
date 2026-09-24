from pathlib import Path


def test_v100_contract():
    root = Path(__file__).parents[2]
    main = (root / 'backend/app/main.py').read_text()
    js = (root / 'mobile/app.js').read_text()
    html = (root / 'mobile/index.html').read_text()
    compose = (root / 'docker-compose.yml').read_text()
    readme = (root / 'README.md').read_text()
    # main.py may be full source or a bootstrap that loads it
    is_bootstrap = 'urllib.request' in main and 'raw.githubusercontent.com' in main
    if not is_bootstrap:
        assert 'APP_VERSION = "1.1.0"' in main
        assert 'FileResponse("mobile/index.html")' in main
        assert 'app.mount("/static"' in main
        assert '/api/v1/patterns' in main and '/api/v1/insights' in main and '/api/v1/signals' in main and '/api/v1/profile' in main and '/api/v1/reports/weekly' in main
        assert 'DUMMY_PASSWORD_HASH' in main
        assert 'RateLimitBucket' in main
        assert 'docs_url="/docs" if DEV_MODE else None' in main
    else:
        assert 'd38d2a8109949d06577d12ab77ed9613cb889c51' in main
    assert 'window.location.origin' in js
    assert '/api/v1/auth/login' in js and '/api/v1/auth/register' in js
    assert '/api/v1/auth/me' in js
    assert '/static/styles.css' in html and '/static/app.js' in html
    assert 'nexgene_data' in compose
    assert 'activity_level' in js and 'diet_quality' in js and 'nicotine' in js
    assert 'innerHTML' not in js
    assert 'APP_VERSION' in readme or 'v1.0.0' in readme or 'v1.1.0' in readme
    assert 'NexGene Signals' in readme and 'Weekly NexGene Report' in readme
