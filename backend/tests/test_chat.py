"""Chat persistence, permissions, durable retry and private model configuration."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json
import os
from threading import Event
from uuid import UUID,uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,func,select,text
from sqlalchemy.orm import Session
from lifeagent.auth import COOKIE
from lifeagent.main import create_app
from lifeagent.model_client import ModelFailure,config_path
from lifeagent.models import AuditLog,CalendarEvent,ChatMessage,Conversation,OperationRecord,Task

KEY='test-only-model-key'


def signup(c,email='chat@example.com'):
    r=c.post('/api/v1/auth/register',json={'email':email,'password':'Chat-Test-Password!2026','display_name':'对话测试','timezone':'Asia/Shanghai'})
    assert r.status_code==201
    c.headers['X-CSRF-Token']=r.json()['csrf_token']
    return r.json()


def write(c,path,body=None,method='POST',key=None):
    return c.request(method,'/api/v1'+path,json={} if body is None else body,headers={'Idempotency-Key':key or str(uuid4())})


def configure(c,**changes):
    return write(c,'/model-settings',{'provider':'deepseek','model':'deepseek-flash','api_key':KEY,'consent':True,**changes},'PUT')


def conversation(c):
    r=write(c,'/conversations');assert r.status_code==201,r.text
    return r.json()['id']


def send(c,cid,content='你好',key=None):
    return write(c,f'/conversations/{cid}/messages',{'content':content},key=key)


@pytest.fixture
def chat(postgres_url,monkeypatch,tmp_path):
    monkeypatch.setenv('DATABASE_URL',postgres_url)
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('LIFEAGENT_MODEL_CONFIG_DIR',str(tmp_path/'models'))
    monkeypatch.delenv('APP_ORIGIN',raising=False)
    engine=create_engine(postgres_url)
    with engine.begin() as c:c.execute(text('TRUNCATE users CASCADE'))
    app=create_app();calls=[]
    def model(config,messages):
        assert config.api_key.get_secret_value()==KEY
        calls.append(messages)
        return '测试响应：'+messages[-1]['content']
    app.state.model_client=model
    with TestClient(app) as c:
        profile=signup(c)
        yield c,engine,app,profile,calls
    engine.dispose()


def test_model_settings_private_files_consent_and_account_isolation(chat):
    c,_,app,profile,_=chat
    assert not c.get('/api/v1/model-settings').json()['configured']
    assert configure(c).status_code==200
    path=config_path(profile['user']['id']);assert path.stat().st_mode&0o777==0o600
    assert KEY in path.read_text()
    public=c.get('/api/v1/model-settings');assert KEY not in public.text and 'api_key' not in public.json()
    assert configure(c,api_key=None,model='other-model').status_code==200
    assert configure(c,api_key=None,provider='qwen-cn').status_code==422
    assert configure(c,consent=False).status_code==422
    assert configure(c,api_key='bad\nheader').status_code==422
    assert configure(c,workspace='../unsafe').status_code==422
    assert write(c,'/model-settings',{'provider':'deepseek','model':'x','api_key':KEY,'consent':True,'base_url':'http://127.0.0.1'},'PUT').status_code==422
    with TestClient(app) as other:
        other_profile=signup(other,'other@example.com')
        assert not other.get('/api/v1/model-settings').json()['configured']
        assert write(other,'/model-settings',method='DELETE').status_code==200
        assert path.exists() and not config_path(other_profile['user']['id']).exists()
    result=write(c,'/model-settings/test');assert result.status_code==200 and result.json()['ok']
    assert KEY not in result.text


def test_unconfigured_message_does_not_persist_or_call(chat):
    c,engine,_,_,calls=chat
    cid=conversation(c)
    assert send(c,cid).status_code==409
    assert calls==[]
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(ChatMessage))==0
    assert write(c,'/model-settings/test').status_code==409


def test_chat_history_context_replay_and_no_business_writes(chat):
    c,engine,_,_,calls=chat;configure(c);cid=conversation(c);key=str(uuid4())
    first=send(c,cid,'帮我创建明天的日程',key);assert first.status_code==201,first.text
    replay=send(c,cid,'帮我创建明天的日程',key);assert replay.status_code==201
    assert first.json()['items']==replay.json()['items'] and len(calls)==1
    assert send(c,cid,'改变内容',key).status_code==409
    assert len(calls[0])==2 and 'Asia/Shanghai' in calls[0][0]['content']
    assert send(c,cid,'继续讨论').status_code==201
    assert [m['role'] for m in calls[-1]]==['system','user','assistant','user']
    assert '工具' in calls[-1][0]['content']
    separate=conversation(c);assert send(c,separate,'另一会话').status_code==201
    assert len(calls[-1])==2 and all('帮我创建' not in m['content'] for m in calls[-1])
    history=c.get('/api/v1/conversations/'+cid).json()
    assert [m['sequence'] for m in history['items']]==[1,2,3,4]
    assert history['conversation']['title']=='帮我创建明天的日程'
    page=c.get('/api/v1/conversations/'+cid,params={'limit':2}).json();assert page['has_more']
    assert [m['sequence'] for m in page['items']]==[3,4]
    older=c.get('/api/v1/conversations/'+cid,params={'before':3,'limit':2}).json();assert not older['has_more']
    assert [m['sequence'] for m in older['items']]==[1,2]
    with Session(engine) as db:
        for model in (CalendarEvent,Task):assert db.scalar(select(func.count()).select_from(model))==0
        assert all('帮我创建' not in a.action for a in db.scalars(select(AuditLog)))


def test_auth_csrf_and_cross_account_chat_access(chat):
    c,_,app,_,calls=chat;configure(c);cid=conversation(c);assistant=send(c,cid).json()['items'][1]
    with TestClient(app) as other:
        assert other.get('/api/v1/model-settings').status_code==401
        assert write(other,'/conversations').status_code==401
        signup(other,'other@example.com')
        assert other.get('/api/v1/conversations').json()['items']==[]
        assert other.get('/api/v1/conversations/'+cid).status_code==404
        assert send(other,cid).status_code==404
        assert write(other,f'/conversations/{cid}/messages/{assistant["id"]}/retry').status_code==404
        assert write(other,'/conversations/'+cid,{'version':3},'DELETE').status_code==404
    csrf=c.headers.pop('X-CSRF-Token');assert write(c,'/conversations').status_code==403;c.headers['X-CSRF-Token']=csrf
    assert c.post('/api/v1/conversations/'+cid+'/messages',json={'content':'无键'}).status_code==422
    assert write(c,'/conversations/'+cid+'/messages',{'content':'x','owner_id':str(uuid4())}).status_code==422
    assert len(calls)==1


def test_failure_retry_preserves_one_user_message_and_hides_exception(chat):
    c,engine,app,_,_=chat;configure(c);cid=conversation(c)
    def fail(*_):raise ModelFailure('MODEL_RATE_LIMITED')
    app.state.model_client=fail
    r=send(c,cid);assert r.status_code==201
    assistant=r.json()['items'][1];assert assistant['status']=='failed' and assistant['can_retry']
    assert assistant['error_code']=='MODEL_RATE_LIMITED'
    app.state.model_client=lambda *_:'恢复成功'
    r=write(c,f'/conversations/{cid}/messages/{assistant["id"]}/retry')
    assert r.status_code==200 and r.json()['items'][1]['content']=='恢复成功'
    assert r.json()['items'][1]['id']==assistant['id'] and r.json()['items'][1]['attempts']==2
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(ChatMessage))==2
    # Unexpected provider exceptions must never expose credentials or raw prompts.
    def unsafe(*_):raise RuntimeError('secret='+KEY)
    app.state.model_client=unsafe
    r=send(c,cid,'另一个问题');assert KEY not in r.text
    assert r.json()['items'][1]['error_code']=='MODEL_UNAVAILABLE'


def test_retry_cap_and_newer_messages_do_not_replay_old_turn(chat):
    c,_,app,_,_=chat;configure(c);cid=conversation(c)
    def fail(*_):raise ModelFailure('MODEL_TIMEOUT')
    app.state.model_client=fail
    assistant=send(c,cid).json()['items'][1];path=f'/conversations/{cid}/messages/{assistant["id"]}/retry'
    for attempt in [2,3]:assert write(c,path).json()['items'][1]['attempts']==attempt
    assert write(c,path).status_code==409
    other=send(c,cid,'新问题').json()['items'][1]
    assert write(c,path).status_code==409
    assert other['status']=='failed'


def test_clear_conversation_cascades_only_messages_and_config_delete_preserves_history(chat):
    c,engine,_,_,_=chat;configure(c);cid=conversation(c)
    secret='PRIVATE-CONVERSATION-CONTENT'
    send(c,cid,secret)
    e=write(c,'/events',{'title':'保留日程','start_at':'2026-12-01T01:00Z','end_at':'2026-12-01T02:00Z'}).json()
    write(c,'/tasks',{'title':'保留待办','event_id':e['id']})
    assert write(c,'/model-settings',method='DELETE').status_code==200
    assert len(c.get('/api/v1/conversations/'+cid).json()['items'])==2
    snapshot=c.get('/api/v1/conversations/'+cid).json()['conversation']
    assert write(c,'/conversations/'+cid,{'version':snapshot['version']-1},'DELETE').status_code==409
    key=str(uuid4())
    for _ in range(2):assert write(c,'/conversations/'+cid,{'version':snapshot['version']},'DELETE',key).status_code==200
    assert c.get('/api/v1/conversations/'+cid).status_code==404
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage))==0
        assert db.scalar(select(func.count()).select_from(CalendarEvent))==1
        assert db.scalar(select(func.count()).select_from(Task))==1
        assert all(secret not in json.dumps(r.result) for r in db.scalars(select(OperationRecord)))


def test_inflight_replay_busy_and_refresh_recover_without_duplicate_calls(chat):
    c,engine,app,profile,calls=chat;configure(c);cid=conversation(c);key=str(uuid4());started=Event();release=Event()
    def slow(config,messages):
        calls.append(messages);started.set();assert release.wait(10);return '完成'
    app.state.model_client=slow
    cookie=c.cookies.get(COOKIE)
    def first():
        with TestClient(app) as peer:
            peer.cookies.set(COOKIE,cookie);peer.headers['X-CSRF-Token']=profile['csrf_token']
            return send(peer,cid,'等待',key)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(first)
        try:
            assert started.wait(10)
            snapshot=c.get('/api/v1/conversations/'+cid).json();assert snapshot['items'][1]['status']=='pending'
            assert send(c,cid,'等待',key).status_code==202
            assert send(c,cid,'第二条').status_code==409
            assert write(c,f'/conversations/{cid}/messages/{snapshot["items"][1]["id"]}/retry').status_code==202
        finally:release.set()
        assert future.result(10).status_code==201
    assert len(calls)==1
    assert c.get('/api/v1/conversations/'+cid).json()['items'][1]['status']=='complete'


def test_stale_lease_can_retry_and_deleted_conversation_cannot_resurrect(chat):
    c,engine,app,_,_=chat;configure(c);cid=conversation(c);assistant=send(c,cid).json()['items'][1]
    with Session(engine) as db:
        item=db.get(ChatMessage,UUID(assistant['id']));item.status='pending';item.lease_until=datetime.now(timezone.utc)-timedelta(seconds=1);item.lease_token=uuid4();db.commit()
    snapshot=c.get('/api/v1/conversations/'+cid).json()['items'][1]
    assert snapshot['status']=='failed' and snapshot['error_code']=='MODEL_INTERRUPTED'
    assert write(c,f'/conversations/{cid}/messages/{assistant["id"]}/retry').json()['items'][1]['attempts']==2
    v=c.get('/api/v1/conversations/'+cid).json()['conversation']['version']
    assert write(c,'/conversations/'+cid,{'version':v},'DELETE').status_code==200
    assert send(c,cid).status_code==404


def test_migration_roundtrip_keeps_calendar_and_account(chat):
    from alembic import command
    from lifeagent.database import migration_config
    c,_,_,profile,_=chat
    e=write(c,'/events',{'title':'迁移保留','start_at':'2026-12-02T01:00Z','end_at':'2026-12-02T02:00Z'}).json()
    command.downgrade(migration_config(),'0003_calendar_tasks')
    command.upgrade(migration_config(),'head');command.upgrade(migration_config(),'head')
    assert c.get('/api/v1/me').json()['user']['id']==profile['user']['id']
    assert c.get('/api/v1/events/'+e['id']).json()['title']=='迁移保留'
    assert conversation(c)


def test_late_response_cannot_overwrite_completed_retry(chat):
    c,engine,app,profile,_=chat;configure(c);cid=conversation(c);started=Event();release=Event();counter=[]
    def model(*_):
        counter.append(1)
        if len(counter)==1:
            started.set();assert release.wait(10);return '旧响应'
        return '新响应'
    app.state.model_client=model;cookie=c.cookies.get(COOKIE)
    def first():
        with TestClient(app) as peer:
            peer.cookies.set(COOKIE,cookie);peer.headers['X-CSRF-Token']=profile['csrf_token']
            return send(peer,cid)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(first)
        try:
            assert started.wait(10)
            with Session(engine) as db:
                pending=db.scalar(select(ChatMessage).where(ChatMessage.conversation_id==UUID(cid),ChatMessage.role=='assistant'))
                mid=str(pending.id);pending.lease_until=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
            result=write(c,f'/conversations/{cid}/messages/{mid}/retry')
            assert result.json()['items'][1]['content']=='新响应'
        finally:release.set()
        assert future.result(10).json()['items'][1]['content']=='新响应'
    assert c.get('/api/v1/conversations/'+cid).json()['items'][1]['content']=='新响应'


def test_context_and_message_rate_are_bounded(chat):
    c,_,_,_,calls=chat;configure(c);cid=conversation(c)
    for n in range(20):assert send(c,cid,str(n)).status_code==201
    assert len(calls)==20 and len(calls[-1])<=26
    assert send(c,cid,'超过限额').status_code==429
    assert len(calls)==20


def test_connection_probe_releases_database_before_external_call(chat):
    c,engine,app,_,_=chat;configure(c)
    def inspect(*_):
        with engine.connect() as connection:
            count=connection.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction' AND pid<>pg_backend_pid()"))
            assert count==0
        return '连接成功'
    app.state.model_client=inspect
    assert write(c,'/model-settings/test').status_code==200


@pytest.mark.parametrize('content',['   ','\x00','x'*4001])
def test_invalid_chat_input_never_calls_model(chat,content):
    c,engine,_,_,calls=chat;configure(c);cid=conversation(c)
    assert send(c,cid,content).status_code==422
    assert not calls
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(ChatMessage))==0


def test_deleting_during_external_call_never_resurrects_history(chat):
    c,engine,app,profile,_=chat;configure(c);cid=conversation(c);started=Event();release=Event();cookie=c.cookies.get(COOKIE)
    def slow(*_):started.set();assert release.wait(10);return '过迟的回复'
    app.state.model_client=slow
    def first():
        with TestClient(app) as peer:
            peer.cookies.set(COOKIE,cookie);peer.headers['X-CSRF-Token']=profile['csrf_token']
            return send(peer,cid)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(first)
        try:
            assert started.wait(10)
            v=c.get('/api/v1/conversations/'+cid).json()['conversation']['version']
            assert write(c,'/conversations/'+cid,{'version':v},'DELETE').status_code==200
        finally:release.set()
        assert future.result(10).status_code==404
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Conversation))==0
        assert db.scalar(select(func.count()).select_from(ChatMessage))==0
