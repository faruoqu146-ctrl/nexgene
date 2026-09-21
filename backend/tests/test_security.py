import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient
from backend.app.main import app

client=TestClient(app)

def strong(n='A_secure_password!9'):
    return {'email': 'security@example.com', 'password': n}

def test_password_policy():
    r=client.post('/api/v1/auth/register',json={'email':'weak@example.com','password':'password'})
    assert r.status_code in (400,422)

def test_cookie_auth_and_csrf():
    r=client.post('/api/v1/auth/register',json=strong('A_secure_password!9'))
    assert r.status_code in (200,409)
    if r.status_code==409:
        r=client.post('/api/v1/auth/login',json=strong('A_secure_password!9'))
        assert r.status_code==200
    assert 'nexgene_session' in r.cookies
    bad=client.post('/api/v1/checkins/morning',json={'values':{'energy':8}})
    assert bad.status_code==403
    csrf=r.cookies.get('nexgene_csrf')
    good=client.post('/api/v1/checkins/morning',json={'values':{'energy':8}},headers={'X-CSRF-Token':csrf})
    assert good.status_code==200

def test_logout_revokes_session():
    r=client.post('/api/v1/auth/login',json=strong('A_secure_password!9'))
    csrf=r.cookies.get('nexgene_csrf')
    out=client.post('/api/v1/auth/logout',headers={'X-CSRF-Token':csrf})
    assert out.status_code==200
    assert client.get('/api/v1/auth/me').status_code==401
