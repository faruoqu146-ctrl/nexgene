from pathlib import Path

def test_v07_contract():
    root=Path(__file__).parents[2]
    main=(root/'backend/app/main.py').read_text()
    js=(root/'mobile/app.js').read_text()
    html=(root/'mobile/index.html').read_text()
    assert 'version="0.7.0"' in main
    assert '/api/v1/patterns' in main
    assert '/api/v1/insights' in main
    assert 'showView(\'patterns\')' in html
    assert 'loadPatterns' in js
    assert 'activity_level' in js and 'diet_quality' in js and 'nicotine' in js
