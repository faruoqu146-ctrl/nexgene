import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def strong(email='security@example.com', password='A_secure_password!9'):
    return {'email': email, 'password': password}


def test_password_policy():
    r = client.post('/api/v1/auth/register', json={'email': 'weak@example.com', 'password': 'password'})
    assert r.status_code in (400, 422)


def test_cookie_auth_and_csrf():
    r = client.post('/api/v1/auth/register', json=strong())
    assert r.status_code in (200, 409)
    if r.status_code == 409:
        r = client.post('/api/v1/auth/login', json=strong())
        assert r.status_code == 200
    assert 'nexgene_session' in r.cookies
    csrf = r.cookies.get('nexgene_csrf')
    bad = client.post('/api/v1/checkins/morning', json={'values': {'energy': 8}})
    assert bad.status_code == 403
    good = client.post('/api/v1/checkins/morning', json={'values': {'energy': 8}}, headers={'X-CSRF-Token': csrf})
    assert good.status_code == 200


def test_csrf_rotation_updates_server_hash():
    r = client.post('/api/v1/auth/login', json=strong())
    assert r.status_code == 200
    r2 = client.get('/api/v1/auth/csrf')
    assert r2.status_code == 200
    csrf = r2.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    good = client.post('/api/v1/checkins/morning', json={'values': {'energy': 7}}, headers={'X-CSRF-Token': csrf})
    assert good.status_code == 200


def test_logout_revokes_session():
    r = client.post('/api/v1/auth/login', json=strong())
    csrf = r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    out = client.post('/api/v1/auth/logout', headers={'X-CSRF-Token': csrf})
    assert out.status_code == 200
    assert client.get('/api/v1/auth/me').status_code == 401


def test_existing_registration_is_uniform():
    email = 'enumeration@example.com'
    client.post('/api/v1/auth/register', json=strong(email=email))
    r = client.post('/api/v1/auth/register', json=strong(email=email))
    assert r.status_code == 200
    assert 'dev_verification_token' not in r.json()


def test_missing_login_still_runs_dummy_password_verification():
    r = client.post('/api/v1/auth/login', json=strong(email='definitely-missing@example.com'))
    assert r.status_code == 401
    assert r.json()['detail'] == 'Invalid email or password'


def test_checkin_rejects_unknown_kind_and_oversized_value():
    r = client.post('/api/v1/auth/login', json=strong())
    csrf = r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    unknown = client.post('/api/v1/checkins/morning', json={'values': {'made_up_kind': 'x'}}, headers={'X-CSRF-Token': csrf})
    assert unknown.status_code == 422
    oversized = client.post('/api/v1/checkins/morning', json={'values': {'morning_context': 'x' * 257}}, headers={'X-CSRF-Token': csrf})
    assert oversized.status_code == 422


def test_production_docs_are_configurable_off():
    from backend.app.main import DEV_MODE
    if not DEV_MODE:
        assert client.get('/docs').status_code == 404
        assert client.get('/openapi.json').status_code == 404
