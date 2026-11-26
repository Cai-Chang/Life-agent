"""Business invariants exercised against a fresh real PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session

from lifeagent.auth import COOKIE
from lifeagent.main import create_app
from lifeagent.models import CalendarEvent, Task, OperationRecord, AuditLog


@pytest.fixture
def planning(postgres_url, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', postgres_url)
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.delenv('APP_ORIGIN', raising=False)
    engine = create_engine(postgres_url)
    with engine.begin() as c:
        c.execute(text('TRUNCATE users CASCADE'))
    app = create_app()
    with TestClient(app) as client:
        profile = signup(client)
        client.headers['X-CSRF-Token'] = profile['csrf_token']
        yield client, engine, app, profile
    engine.dispose()


def signup(client, email='planner@example.com'):
    r = client.post('/api/v1/auth/register', json={'email':email, 'password':'Planning-Test-Password!2026', 'display_name':'计划测试', 'timezone':'Asia/Shanghai'})
    assert r.status_code == 201
    return r.json()


def write(c, path, body, method='POST', key=None):
    return c.request(method, '/api/v1'+path, json=body, headers={'Idempotency-Key':key or str(uuid4())})


def event(c, **changes):
    return write(c, '/events', {'title':'学习时间','start_at':'2026-12-01T09:00:00+08:00','end_at':'2026-12-01T10:00:00+08:00', **changes})


def listed(c, kind='events', **params):
    defaults={'start':'2026-12-01T00:00:00Z','end':'2027-01-01T00:00:00Z'} if kind=='events' else {}
    return c.get('/api/v1/'+kind,params={**defaults,**params})


def test_event_crud_utc_boundaries_and_cancel_keeps_task(planning):
    c, engine, _, _ = planning
    r=event(c);assert r.status_code==201,r.text
    e=r.json();assert e['start_at']=='2026-12-01T01:00:00+00:00'
    assert c.get('/api/v1/events/'+e['id']).json()==e
    assert len(listed(c).json()['items'])==1
    t=write(c,'/tasks',{'title':'关联待办','event_id':e['id']}).json()
    # Adjacent end points and a cross-offset equivalent are handled correctly.
    assert event(c,start_at='2026-12-01T02:00:00Z',end_at='2026-12-01T03:00:00Z').status_code==201
    assert event(c,start_at='2026-12-01T01:59:59Z',end_at='2026-12-01T04:00:00Z').status_code==409
    r=write(c,'/events/'+e['id'],{'version':1,'title':'改名'},'PATCH');assert r.status_code==200
    assert r.json()['version']==2
    r=write(c,'/events/'+e['id'],{'version':2},'DELETE');assert r.json()['status']=='cancelled'
    assert c.get('/api/v1/tasks/'+t['id']).json()['event_id']==e['id']
    assert len(listed(c,status='active').json()['items'])==1
    assert event(c).status_code==201
    restore=write(c,'/events/'+e['id'],{'version':3,'status':'active'},'PATCH')
    assert restore.status_code==409 and restore.json()['error']['code']=='EVENT_CONFLICT'
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Task))==1


@pytest.mark.parametrize('changes',[
    {'start_at':'2026-12-01T09:00:00'}, {'end_at':'2026-12-01T01:00:00Z'},
    {'title':'   '}, {'end_at':None}, {'owner_id':str(uuid4())}, {'description':'x'*4001},
])
def test_invalid_event_rejected_atomically(planning,changes):
    c,engine,_,_=planning
    assert event(c,**changes).status_code==422
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CalendarEvent))==0
        assert db.scalar(select(func.count()).select_from(OperationRecord))==0


def test_event_edit_conflict_and_stale_version_roll_back(planning):
    c,_,_,_=planning
    e=event(c).json()
    second=event(c,start_at='2026-12-01T03:00Z',end_at='2026-12-01T04:00Z').json()
    r=write(c,'/events/'+e['id'],{'version':1,'title':'不应保存','end_at':'2026-12-01T03:30Z'},'PATCH')
    assert r.status_code==409
    assert c.get('/api/v1/events/'+e['id']).json()==e
    assert write(c,'/events/'+e['id'],{'version':1,'title':'已保存'},'PATCH').status_code==200
    assert write(c,'/events/'+e['id'],{'version':1,'title':'旧页面'},'PATCH').status_code==409
    assert write(c,'/events/'+second['id'],{'version':1,'start_at':None},'PATCH').status_code==422


def test_task_states_filters_clear_due_priority_and_delete(planning):
    c,_,_,_=planning
    t=write(c,'/tasks',{'title':'买书','priority':'high','due_at':'2026-12-01T18:00+08:00'}).json()
    assert t['status']=='pending' and t['due_at']=='2026-12-01T10:00:00+00:00'
    assert len(listed(c,'tasks',due_start='2026-12-01T10:00Z',due_end='2026-12-02T00:00Z').json()['items'])==1
    assert not listed(c,'tasks',due_end='2026-12-01T10:00Z').json()['items']
    for version,status in [(1,'in_progress'),(2,'done')]:
        assert write(c,'/tasks/'+t['id'],{'version':version,'status':status},'PATCH').status_code==200
    assert len(listed(c,'tasks',status='done').json()['items'])==1
    assert write(c,'/tasks/'+t['id'],{'version':3,'status':'in_progress'},'PATCH').status_code==409
    reopened=write(c,'/tasks/'+t['id'],{'version':3,'status':'pending','due_at':None,'priority':'low','description':'备注'},'PATCH').json()
    assert reopened['due_at'] is None and reopened['version']==4
    assert write(c,'/tasks/'+t['id'],{'version':3},'DELETE').status_code==409
    key=str(uuid4())
    for _ in range(2):assert write(c,'/tasks/'+t['id'],{'version':4},'DELETE',key).json()['deleted']
    assert c.get('/api/v1/tasks/'+t['id']).status_code==404


def test_pagination_and_invalid_filters(planning):
    c,_,_,_=planning
    for n in range(3):assert write(c,'/tasks',{'title':str(n)}).status_code==201
    page=listed(c,'tasks',limit=2).json();assert page['has_more']
    tail=listed(c,'tasks',limit=2,offset=2).json();assert not tail['has_more']
    assert len({v['id'] for v in page['items']+tail['items']})==3
    assert listed(c,'tasks',status='invalid').status_code==422
    assert listed(c,start='2026-12-02T00:00Z',end='2026-12-01T00:00Z').status_code==422
    assert listed(c,start='2026-12-01T00:00',end='2026-12-02T00:00Z').status_code==422
    assert listed(c,offset=-1).status_code==422


def test_cross_account_access_and_forged_links_are_rejected(planning):
    c,_,app,_=planning
    e=event(c).json();t=write(c,'/tasks',{'title':'私有'}).json()
    with TestClient(app) as other:
        profile=signup(other,'other@example.com');other.headers['X-CSRF-Token']=profile['csrf_token']
        assert listed(other).json()['items']==[] and listed(other,'tasks').json()['items']==[]
        for kind,item in [('events',e),('tasks',t)]:
            assert other.get('/api/v1/'+kind+'/'+item['id']).status_code==404
            assert write(other,'/'+kind+'/'+item['id'],{'version':1,'title':'攻击'},'PATCH').status_code==404
            assert write(other,'/'+kind+'/'+item['id'],{'version':1},'DELETE').status_code==404
        assert write(other,'/tasks',{'title':'伪造关联','event_id':e['id']}).status_code==404
        own=write(other,'/tasks',{'title':'自己的'}).json()
        assert write(other,'/tasks/'+own['id'],{'version':1,'event_id':e['id']},'PATCH').status_code==404
    assert c.get('/api/v1/tasks/'+t['id']).json()['title']=='私有'


def test_auth_csrf_idempotency_and_audit(planning):
    c,engine,app,_=planning
    with TestClient(app) as anonymous:
        assert listed(anonymous).status_code==401
        assert write(anonymous,'/tasks',{'title':'无身份'}).status_code==401
    assert c.post('/api/v1/tasks',json={'title':'无标识'}).status_code==422
    assert c.post('/api/v1/tasks',json={'title':'跨站'},headers={'Origin':'https://attacker.example'}).status_code==403
    csrf=c.headers.pop('X-CSRF-Token')
    assert write(c,'/tasks',{'title':'伪造请求'}).status_code==403
    c.headers['X-CSRF-Token']=csrf
    key=str(uuid4());body={'title':'敏感正文不写审计'}
    first=write(c,'/tasks',body,key=key);replay=write(c,'/tasks',body,key=key)
    assert first.status_code==201 and first.json()==replay.json()
    assert write(c,'/tasks',{'title':'不同内容'},key=key).status_code==409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Task))==1
        assert db.scalar(select(func.count()).select_from(OperationRecord))==1
        assert db.scalars(select(AuditLog.action).where(AuditLog.action=='task.create')).all()==['task.create']
        assert str(db.scalar(select(AuditLog.target_id).where(AuditLog.action=='task.create')))==first.json()['id']


def parallel(planning, function):
    c,_,app,profile=planning
    cookie=c.cookies.get(COOKIE);barrier=Barrier(2)
    def execute(n):
        with TestClient(app) as peer:
            peer.cookies.set(COOKIE,cookie);peer.headers['X-CSRF-Token']=profile['csrf_token']
            barrier.wait(timeout=10)
            return function(peer,n)
    with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(execute,range(2)))


def test_parallel_overlapping_events_only_one_commits(planning):
    results=parallel(planning,lambda c,n:event(c,title=str(n)))
    assert sorted(v.status_code for v in results)==[201,409]
    assert len(listed(planning[0]).json()['items'])==1


def test_parallel_same_operation_has_one_record(planning):
    key=str(uuid4())
    results=parallel(planning,lambda c,n:write(c,'/tasks',{'title':'同一操作'},key=key))
    assert [v.status_code for v in results]==[201,201]
    assert results[0].json()==results[1].json()
    assert len(listed(planning[0],'tasks').json()['items'])==1


def test_parallel_edits_reject_lost_update(planning):
    t=write(planning[0],'/tasks',{'title':'原内容'}).json()
    results=parallel(planning,lambda c,n:write(c,'/tasks/'+t['id'],{'version':1,'title':str(n)},'PATCH'))
    assert sorted(v.status_code for v in results)==[200,409]
    assert planning[0].get('/api/v1/tasks/'+t['id']).json()['version']==2


def test_migration_roundtrip_preserves_existing_account(planning):
    from alembic import command
    from lifeagent.database import migration_config
    c,engine,_,profile=planning
    config=migration_config()
    # Only this fixture's disposable database; no user/development DB is used.
    command.downgrade(config,'0002_auth_personal')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM users'))==1
    command.upgrade(config,'head')
    command.upgrade(config,'head')
    assert c.get('/api/v1/me').json()['user']['id']==profile['user']['id']
    assert event(c).status_code==201
