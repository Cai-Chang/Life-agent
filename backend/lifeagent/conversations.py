"""Personal chat history and explicit model calls; no business tools execute here."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator
from sqlalchemy import func, select

from lifeagent.auth import Auth, DB, Input, audit, owned_workspace, problem
from lifeagent.models import ChatMessage, Conversation, Workspace
from lifeagent.planning import Deletion, check_version, mutation
from lifeagent.model_client import ERRORS, ModelFailure, ModelSettings, complete, public_settings, read_config, remove_config, save_config

router = APIRouter(prefix='/api/v1')


class ConversationInput(Input):
    title: str = Field(default='新对话', min_length=1, max_length=80)

    @field_validator('title')
    @classmethod
    def nonempty(cls, value):
        if not value.strip() or '\x00' in value:
            raise ValueError('会话标题不能为空或包含空字符')
        return value.strip()


class MessageInput(Input):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator('content')
    @classmethod
    def nonempty(cls, value):
        if not value.strip() or '\x00' in value:
            raise ValueError('消息不能为空或包含空字符')
        return value.strip()


def conversation_data(item):
    return {'id':str(item.id), 'title':item.title, 'version':item.version,
        'created_at':item.created_at.astimezone(timezone.utc).isoformat(),
        'updated_at':item.updated_at.astimezone(timezone.utc).isoformat()}


def message_data(item, latest_sequence=None):
    stale = item.status == 'pending' and item.lease_until <= datetime.now(timezone.utc)
    code = 'MODEL_INTERRUPTED' if stale else item.error_code
    return {'id':str(item.id), 'sequence':item.sequence, 'role':item.role,
        'content':item.content, 'status':'failed' if stale else item.status,
        'error_code':code, 'error_message':ERRORS.get(code, '') if code else '',
        'attempts':item.attempts, 'can_retry':item.role=='assistant' and (stale or item.status=='failed') and item.attempts<3 and (latest_sequence is None or item.sequence==latest_sequence),
        'model':item.model, 'created_at':item.created_at.astimezone(timezone.utc).isoformat()}


def owned_conversation(db, identity, item_id, lock=False):
    space = owned_workspace(db, identity.user)
    if lock:
        db.execute(select(Workspace.id).where(Workspace.id==space.id).with_for_update()).one()
    query = select(Conversation).where(Conversation.id==item_id, Conversation.workspace_id==space.id, Conversation.owner_id==identity.user.id)
    if lock:
        query = query.with_for_update()
    item = db.scalar(query.execution_options(populate_existing=True))
    if item is None:
        raise problem(404, 'NOT_FOUND', '会话不存在或你无权访问')
    return item


def pair_response(db, conversation, assistant, code=200):
    user = db.scalar(select(ChatMessage).where(ChatMessage.conversation_id==conversation.id,
        ChatMessage.turn_key==assistant.turn_key, ChatMessage.role=='user'))
    return JSONResponse({'conversation':conversation_data(conversation), 'items':[message_data(user,conversation.next_sequence-1),message_data(assistant,conversation.next_sequence-1)]}, status_code=code)


def key_for(request):
    key = request.headers.get('Idempotency-Key', '')
    if not 8 <= len(key) <= 128 or not key.isascii() or not all(c.isalnum() or c in '-_.' for c in key):
        raise problem(422, 'OPERATION_KEY_REQUIRED', '请提供有效的操作标识后重试')
    return key


def context(db, conversation, identity, question):
    completed = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id==conversation.id,
        ChatMessage.role=='assistant', ChatMessage.status=='complete').order_by(ChatMessage.sequence.desc()).limit(12)).all()
    turns = []
    remaining = 24000-len(question)
    for assistant in completed:
        user = db.scalar(select(ChatMessage).where(ChatMessage.conversation_id==conversation.id,
            ChatMessage.turn_key==assistant.turn_key, ChatMessage.role=='user'))
        cost = len(user.content)+len(assistant.content)
        if cost > remaining:
            break
        remaining -= cost
        turns.append([{'role':'user','content':user.content},{'role':'assistant','content':assistant.content}])
    now = datetime.now(timezone.utc).astimezone(ZoneInfo(identity.user.timezone))
    system = ('你是 LifeAgent 生活助理，使用用户的语言简洁回复，可以讨论日程、待办和生活安排。'
        f'用户时区为 {identity.user.timezone}，当前本地时间为 {now.isoformat()}。'
        '当前阶段只有对话功能，没有读取、创建或修改日程待办、联网查询或执行任务的工具。'
        '不要声称已经完成任何实际写入或执行。需要录入时请指导用户前往日程或待办页面手动保存。'
        '信息不足时先追问，不要编造已有日程、任务执行结果或隐私数据。')
    messages = [{'role':'system','content':system}]
    for turn in reversed(turns):
        messages.extend(turn)
    messages.append({'role':'user','content':question})
    return messages


def active_other(db, conversation, now, except_id=None):
    query = select(ChatMessage).where(ChatMessage.conversation_id==conversation.id,
        ChatMessage.role=='assistant', ChatMessage.status=='pending')
    if except_id:
        query = query.where(ChatMessage.id!=except_id)
    for item in db.scalars(query):
        if item.lease_until > now:
            raise problem(409, 'CONVERSATION_BUSY', '这个会话正在回复，请等待完成后再发送。')
        item.status = 'failed'
        item.error_code = 'MODEL_INTERRUPTED'


def model_budget(db, conversation, now):
    scope = [Conversation.workspace_id==conversation.workspace_id, Conversation.owner_id==conversation.owner_id,
        ChatMessage.role=='assistant']
    count = db.scalar(select(func.count()).select_from(ChatMessage).join(Conversation).where(
        *scope, ChatMessage.created_at>=now-timedelta(minutes=1)))
    if count >= 20:
        raise problem(429, 'CHAT_RATE_LIMITED', '发送过于频繁，请稍后再试。')
    pending = db.scalar(select(func.count()).select_from(ChatMessage).join(Conversation).where(
        *scope, ChatMessage.status=='pending', ChatMessage.lease_until>now))
    if pending >= 2:
        raise problem(429, 'CHAT_BUSY', '已有两个会话正在回复，请稍后再试。')


def run_model(request, db, identity, conversation, assistant, config, messages, response_code):
    conversation_id, assistant_id, lease = conversation.id, assistant.id, assistant.lease_token
    db.commit()  # Release all database locks/connections before the external call.
    failure = None
    result = ''
    try:
        client = getattr(request.app.state, 'model_client', complete)
        result = client(config, messages)
        if not isinstance(result,str) or not result.strip() or len(result)>16000:
            raise ModelFailure('MODEL_INVALID_RESPONSE')
    except ModelFailure as exc:
        failure = exc.code
    except Exception:
        # Never expose provider exceptions: they may contain headers or prompts.
        failure = 'MODEL_UNAVAILABLE'
    conversation = owned_conversation(db, identity, conversation_id, lock=True)
    current = db.scalar(select(ChatMessage).where(ChatMessage.id==assistant_id,
        ChatMessage.conversation_id==conversation_id).execution_options(populate_existing=True))
    if current is None:
        raise problem(404, 'NOT_FOUND', '会话已清除')
    # A late response must not overwrite a retry, a newer turn or an expired lease.
    if current.status!='pending' or current.lease_token!=lease or current.lease_until<=datetime.now(timezone.utc):
        return pair_response(db, conversation, current)
    current.status = 'failed' if failure else 'complete'
    current.error_code = failure
    current.content = '' if failure else result.strip()
    current.lease_token = None
    current.lease_until = None
    conversation.updated_at = datetime.now(timezone.utc)
    conversation.version += 1
    audit(db, identity.user, 'chat.failed' if failure else 'chat.completed', conversation.workspace_id, assistant_id)
    db.commit()
    return pair_response(db, conversation, current, response_code)


@router.get('/model-settings')
def settings(identity: Auth):
    return public_settings(identity.user.id)


@router.put('/model-settings')
def configure(body: ModelSettings, identity: Auth):
    return save_config(identity.user.id, body)


@router.delete('/model-settings')
def clear_settings(body: Input, identity: Auth):
    remove_config(identity.user.id)
    return public_settings(identity.user.id)


@router.post('/model-settings/test')
def test_settings(body: Input, request: Request, db: DB, identity: Auth):
    config = read_config(identity.user.id)
    if config is None:
        raise problem(409, 'MODEL_NOT_CONFIGURED', '请先保存模型配置。')
    db.commit()  # The connection check must not hold an authentication transaction.
    try:
        reply = getattr(request.app.state,'model_client',complete)(config,
            [{'role':'system','content':'请简短回复。'},{'role':'user','content':'请回复：连接成功。'}])
        return {'ok':True, 'model':config.model, 'reply':reply}
    except ModelFailure as exc:
        raise problem(502, exc.code, str(exc)) from None
    except Exception:
        raise problem(502,'MODEL_UNAVAILABLE',ERRORS['MODEL_UNAVAILABLE']) from None


@router.get('/conversations')
def conversations(db: DB, identity: Auth, offset: int = Query(0,ge=0), limit: int = Query(50,ge=1,le=100)):
    space = owned_workspace(db, identity.user)
    items = db.scalars(select(Conversation).where(Conversation.owner_id==identity.user.id,
        Conversation.workspace_id==space.id).order_by(Conversation.updated_at.desc(),Conversation.id).offset(offset).limit(limit+1)).all()
    return {'items':[conversation_data(v) for v in items[:limit]], 'has_more':len(items)>limit}


@router.post('/conversations', status_code=201)
def create_conversation(body: ConversationInput, request: Request, db: DB, identity: Auth):
    def write(workspace):
        item = Conversation(workspace_id=workspace.id,owner_id=identity.user.id,title=body.title)
        db.add(item)
        db.flush()
        audit(db,identity.user,'conversation.create',workspace.id,item.id)
        # Only retain the ID in the replay record; clearing history must clear text.
        return {'id':str(item.id)},201
    return mutation(request,body,db,identity,write)


@router.get('/conversations/{item_id}')
def get_conversation(item_id: UUID, db: DB, identity: Auth, before: int | None = Query(None,ge=1), limit: int = Query(100,ge=1,le=100)):
    conversation = owned_conversation(db,identity,item_id)
    query = select(ChatMessage).where(ChatMessage.conversation_id==conversation.id)
    if before:
        query = query.where(ChatMessage.sequence<before)
    items = db.scalars(query.order_by(ChatMessage.sequence.desc()).limit(limit+1)).all()
    return {'conversation':conversation_data(conversation), 'items':[message_data(v,conversation.next_sequence-1) for v in reversed(items[:limit])], 'has_more':len(items)>limit}


@router.delete('/conversations/{item_id}')
def delete_conversation(item_id: UUID, body: Deletion, request: Request, db: DB, identity: Auth):
    def write(workspace):
        item = owned_conversation(db,identity,item_id,lock=True)
        check_version(item,body.version)
        db.delete(item)
        audit(db,identity.user,'conversation.delete',workspace.id,item_id)
        return {'id':str(item_id),'deleted':True},200
    return mutation(request,body,db,identity,write)


@router.post('/conversations/{item_id}/messages', status_code=201)
def send_message(item_id: UUID, body: MessageInput, request: Request, db: DB, identity: Auth):
    key = key_for(request)
    conversation = owned_conversation(db,identity,item_id,lock=True)
    existing = db.scalar(select(ChatMessage).where(ChatMessage.conversation_id==item_id,
        ChatMessage.turn_key==key,ChatMessage.role=='assistant'))
    if existing:
        user = db.scalar(select(ChatMessage).where(ChatMessage.conversation_id==item_id,
            ChatMessage.turn_key==key,ChatMessage.role=='user'))
        if user.content != body.content:
            raise problem(409,'OPERATION_KEY_REUSED','该操作标识已用于其他消息，请重新提交。')
        return pair_response(db,conversation,existing,202 if existing.status=='pending' else 201)
    config = read_config(identity.user.id)
    if config is None:
        raise problem(409,'MODEL_NOT_CONFIGURED','请先配置并保存模型服务，再发送消息。')
    now = datetime.now(timezone.utc)
    active_other(db,conversation,now)
    model_budget(db,conversation,now)
    messages = context(db,conversation,identity,body.content)
    sequence = conversation.next_sequence
    user = ChatMessage(conversation_id=item_id,turn_key=key,sequence=sequence,role='user',content=body.content,status='complete')
    assistant = ChatMessage(id=uuid4(),conversation_id=item_id,turn_key=key,sequence=sequence+1,role='assistant',
        content='',status='pending',lease_token=uuid4(),lease_until=now+timedelta(seconds=120),model=config.model)
    db.add_all([user,assistant])
    conversation.next_sequence += 2
    conversation.version += 1
    conversation.updated_at = now
    if sequence==1:
        conversation.title = body.content[:60]
    audit(db,identity.user,'chat.submitted',conversation.workspace_id,assistant.id)
    return run_model(request,db,identity,conversation,assistant,config,messages,201)


@router.post('/conversations/{item_id}/messages/{message_id}/retry')
def retry_message(item_id: UUID, message_id: UUID, body: Input, request: Request, db: DB, identity: Auth):
    key_for(request)
    conversation = owned_conversation(db,identity,item_id,lock=True)
    assistant = db.scalar(select(ChatMessage).where(ChatMessage.id==message_id,ChatMessage.conversation_id==item_id,
        ChatMessage.role=='assistant').execution_options(populate_existing=True))
    if assistant is None:
        raise problem(404,'NOT_FOUND','消息不存在或你无权访问')
    now = datetime.now(timezone.utc)
    if assistant.status=='complete':
        return pair_response(db,conversation,assistant)
    if assistant.status=='pending' and assistant.lease_until>now:
        return pair_response(db,conversation,assistant,202)
    if assistant.attempts>=3:
        raise problem(409,'RETRY_LIMIT','这条消息已达到重试上限，请稍后发送新消息。')
    # Retrying an older failed turn after a newer turn changes context: refuse it.
    if assistant.sequence!=conversation.next_sequence-1:
        raise problem(409,'RETRY_SUPERSEDED','后面已有新消息，请发送新的问题，不再重试这条旧消息。')
    config = read_config(identity.user.id)
    if config is None:
        raise problem(409,'MODEL_NOT_CONFIGURED','请先配置并保存模型服务。')
    active_other(db,conversation,now,assistant.id)
    model_budget(db,conversation,now)
    user = db.scalar(select(ChatMessage).where(ChatMessage.conversation_id==item_id,
        ChatMessage.turn_key==assistant.turn_key,ChatMessage.role=='user'))
    messages = context(db,conversation,identity,user.content)
    assistant.status='pending'
    assistant.error_code=None
    assistant.lease_token=uuid4()
    assistant.lease_until=now+timedelta(seconds=120)
    assistant.attempts+=1
    assistant.model=config.model
    conversation.version+=1
    conversation.updated_at=now
    audit(db,identity.user,'chat.retried',conversation.workspace_id,assistant.id)
    return run_model(request,db,identity,conversation,assistant,config,messages,200)
