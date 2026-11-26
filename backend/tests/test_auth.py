"""Prevent cross-account access, forged writes, credential leakage, and stale sessions."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session

from lifeagent.auth import COOKIE
from lifeagent.main import create_app
from lifeagent.models import AuditLog, BrowserSession, Membership, User, Workspace

PASSWORD = 'Example-Test-Password!2026'


@pytest.fixture
def setup(postgres_url, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', postgres_url)
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.delenv('APP_ORIGIN', raising=False)
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        connection.execute(text('TRUNCATE users CASCADE'))
    app = create_app()
    with TestClient(app) as client:
        yield client, engine, app
    engine.dispose()


def register(client, email='alice@example.com'):
    return client.post('/api/v1/auth/register', json={'email':email,'password':PASSWORD,'display_name':'小林','timezone':'Asia/Shanghai'})


def test_registration_creates_atomic_personal_workspace_and_secure_session(setup):
    client, engine, _ = setup
    assert client.get('/api/v1/me').status_code == 401
    response = register(client)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['workspace']['type'] == 'personal'
    assert data['workspace']['role'] == 'owner'
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'samesite=lax' in response.headers['set-cookie'].lower()
    assert response.headers['cache-control'] == 'no-store'
    assert PASSWORD not in response.text and 'password_hash' not in response.text
    assert client.get('/api/v1/me').json()['user']['id'] == data['user']['id']
    with Session(engine) as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith('$argon2id$') and user.password_hash != PASSWORD
        token = client.cookies.get(COOKIE)
        assert db.get(BrowserSession, sha256(token.encode()).hexdigest()) is not None
        assert db.scalar(select(func.count()).select_from(Workspace)) == 1
        assert db.scalar(select(func.count()).select_from(Membership)) == 1
        assert db.scalar(select(AuditLog.action)) == 'auth.register'


def test_duplicate_registration_is_case_insensitive_and_rolls_back(setup):
    client, engine, _ = setup
    assert register(client, 'Alice@EXAMPLE.COM').status_code == 201
    assert register(client, 'alice@example.com').status_code == 409
    with Session(engine) as db:
        for model in (User, Workspace, Membership):
            assert db.scalar(select(func.count()).select_from(model)) == 1


def test_login_rotation_logout_and_revoked_cookie(setup):
    client, _, app = setup
    first = register(client).json()
    old_cookie = client.cookies.get(COOKIE)
    assert client.post('/api/v1/auth/login',json={'email':'alice@example.com','password':'wrong'}).status_code == 401
    response = client.post('/api/v1/auth/login',json={'email':'ALICE@example.com','password':PASSWORD})
    assert response.status_code == 200
    assert response.json()['workspace']['id'] == first['workspace']['id']
    with TestClient(app) as old:
        old.cookies.set(COOKIE,old_cookie)
        assert old.get('/api/v1/me').status_code == 401
    token = client.cookies.get(COOKIE)
    assert client.post('/api/v1/auth/logout',json={},headers={'X-CSRF-Token':response.json()['csrf_token']}).status_code == 204
    client.cookies.set(COOKIE,token)
    assert client.get('/api/v1/me').status_code == 401


def test_two_accounts_cannot_read_or_write_each_others_workspace(setup):
    alice, _, app = setup
    a = register(alice).json()
    with TestClient(app) as bob:
        b = register(bob, 'bob@example.com').json()
        assert bob.get('/api/v1/workspaces').json()['items'][0]['id'] == b['workspace']['id']
        assert b['workspace']['id'] != a['workspace']['id']
        path = '/api/v1/workspaces/' + a['workspace']['id']
        assert bob.get(path).status_code == 404
        assert bob.patch(path,json={'name':'恶意覆盖'},headers={'X-CSRF-Token':b['csrf_token']}).status_code == 404
        assert bob.patch('/api/v1/me',json={'id':a['user']['id']},headers={'X-CSRF-Token':b['csrf_token']}).status_code == 422
        assert bob.patch('/api/v1/me',json={'timezone':'UTC'},headers={'X-CSRF-Token':a['csrf_token']}).status_code == 403
    assert alice.get('/api/v1/me').json()['user']['timezone'] == 'Asia/Shanghai'
    assert alice.get('/api/v1/workspaces/'+a['workspace']['id']).json()['name'] == '我的个人空间'


def test_profile_and_workspace_changes_persist_and_require_csrf(setup):
    client, _, _ = setup
    data = register(client).json()
    assert client.patch('/api/v1/me',json={'timezone':'UTC'}).status_code == 403
    headers = {'X-CSRF-Token':data['csrf_token']}
    assert client.patch('/api/v1/me',json={'timezone':'Not/A_Zone'},headers=headers).status_code == 422
    assert client.patch('/api/v1/me',json={'timezone':'UTC','display_name':'小陈'},headers=headers).status_code == 200
    path = '/api/v1/workspaces/'+data['workspace']['id']
    assert client.patch(path,json={'name':'我的学习空间'},headers=headers).status_code == 200
    actual = client.get('/api/v1/me').json()
    assert actual['user']['display_name'] == '小陈' and actual['user']['timezone'] == 'UTC'
    assert actual['workspace']['name'] == '我的学习空间'


def test_invalid_input_is_redacted_and_cross_origin_writes_rejected(setup):
    client, _, _ = setup
    leaked = 'secret123'
    response = client.post('/api/v1/auth/register',json={'email':'bad','password':leaked,'display_name':''})
    assert response.status_code == 422 and leaked not in response.text
    assert client.post('/api/v1/auth/login',json={'email':'a@example.com','password':PASSWORD},headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.post('/api/v1/auth/login',data={'email':'a@example.com','password':PASSWORD}).status_code == 415


def test_expired_session_is_rejected_and_failed_logins_throttled(setup):
    client, engine, _ = setup
    register(client)
    with Session(engine) as db:
        record = db.scalar(select(BrowserSession))
        record.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
        db.commit()
    assert client.get('/api/v1/me').status_code == 401
    statuses = [client.post('/api/v1/auth/login',json={'email':'missing@example.com','password':PASSWORD}).status_code for _ in range(15)]
    assert statuses[-1] == 429 and 401 in statuses


def test_production_requires_https_and_sets_secure_cookie(setup, monkeypatch):
    _, _, _ = setup
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(RuntimeError):
        create_app()
    monkeypatch.setenv('APP_ORIGIN','https://life.example.com')
    with TestClient(create_app(),base_url='https://life.example.com') as client:
        response = register(client,'secure@example.com')
        assert response.status_code == 201
        assert '; secure' in response.headers['set-cookie'].lower()
        assert client.get('/api/v1/me').status_code == 200


def test_simultaneous_registration_does_not_create_duplicate_personal_spaces(setup):
    _, engine, app = setup
    def attempt(i):
        with TestClient(app,client=(f'test-{i}',50000+i)) as client:
            return register(client,'race@example.com').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt,range(2))) == [201,409]
    with Session(engine) as db:
        for model in (User,Workspace,Membership):
            assert db.scalar(select(func.count()).select_from(model)) == 1
