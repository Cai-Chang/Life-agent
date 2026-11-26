"""Manual planning: ownership, UTC, serialized conflicts, versions and replay safety."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, Field, field_validator
from sqlalchemy import select

from lifeagent.auth import Auth, DB, Input, audit, owned_workspace, problem
from lifeagent.models import CalendarEvent, OperationRecord, Task, Workspace

router = APIRouter(prefix='/api/v1')
TaskStatus = Literal['pending', 'in_progress', 'done', 'cancelled']
EventStatus = Literal['active', 'cancelled']
Priority = Literal['low', 'normal', 'high']
STATES = {
    'pending': {'pending', 'in_progress', 'done', 'cancelled'},
    'in_progress': {'in_progress', 'pending', 'done', 'cancelled'},
    'done': {'done', 'pending'}, 'cancelled': {'cancelled', 'pending'},
}


class Content(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=4000)

    @field_validator('title')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('标题不能为空')
        return value.strip()


class EventCreate(Content):
    start_at: AwareDatetime
    end_at: AwareDatetime


class TaskCreate(Content):
    due_at: AwareDatetime | None = None
    priority: Priority = 'normal'
    event_id: UUID | None = None


class EventPatch(Input):
    version: int = Field(ge=1, strict=True)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    status: EventStatus | None = None

    @field_validator('title', 'description', 'start_at', 'end_at', 'status')
    @classmethod
    def not_null(cls, value, info):
        if value is None:
            raise ValueError('该字段不能为空')
        return Content.nonempty(value) if info.field_name == 'title' else value


class TaskPatch(Input):
    version: int = Field(ge=1, strict=True)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    due_at: AwareDatetime | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    event_id: UUID | None = None

    @field_validator('title', 'description', 'status', 'priority')
    @classmethod
    def not_null(cls, value, info):
        if value is None:
            raise ValueError('该字段不能为空')
        return Content.nonempty(value) if info.field_name == 'title' else value


class Deletion(Input):
    version: int = Field(ge=1, strict=True)


def serialize(item):
    fields = ['id', 'workspace_id', 'owner_id', 'title', 'description', 'status', 'version', 'created_at']
    fields += ['start_at', 'end_at'] if isinstance(item, CalendarEvent) else ['due_at', 'priority', 'event_id']
    result = {}
    for key in fields:
        value = getattr(item, key)
        result[key] = value.astimezone(timezone.utc).isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, UUID) else value
    return result


def scoped(db, identity, model):
    workspace = owned_workspace(db, identity.user)
    return select(model).where(model.workspace_id == workspace.id, model.owner_id == identity.user.id)


def resource(db, identity, model, item_id):
    item = db.scalar(scoped(db, identity, model).where(model.id == item_id))
    if item is None:
        raise problem(404, 'NOT_FOUND', '记录不存在或你无权访问')
    return item


def mutation(request, body, db, identity, action):
    key = request.headers.get('Idempotency-Key', '')
    if not 8 <= len(key) <= 128 or not key.isascii() or not all(c.isalnum() or c in '-_.' for c in key):
        raise problem(422, 'OPERATION_KEY_REQUIRED', '请提供有效的操作标识后重试')
    workspace = owned_workspace(db, identity.user)
    # A real row lock serializes ALL writes for the personal workspace, including
    # different operation keys, and keeps conflict check + write in one transaction.
    db.execute(select(Workspace.id).where(Workspace.id == workspace.id).with_for_update()).one()
    digest = sha256(json.dumps([request.method, request.url.path, body.model_dump(mode='json')], sort_keys=True).encode()).hexdigest()
    previous = db.get(OperationRecord, (workspace.id, key))
    if previous:
        if previous.request_hash != digest:
            raise problem(409, 'OPERATION_KEY_REUSED', '此操作标识已用于其他内容，请重新提交')
        return JSONResponse(previous.result, status_code=previous.status_code)
    result, code = action(workspace)
    db.add(OperationRecord(workspace_id=workspace.id, operation_id=key, request_hash=digest, result=result, status_code=code))
    db.commit()
    return JSONResponse(result, status_code=code)


def check_version(item, version):
    if item.version != version:
        raise problem(409, 'VERSION_CONFLICT', '记录已被其他页面修改，请刷新后再编辑')


def check_event(db, identity, item):
    if item.end_at <= item.start_at:
        raise problem(422, 'INVALID_TIME_RANGE', '结束时间必须晚于开始时间')
    if item.status != 'active':
        return
    # no_autoflush prevents a rejected edit from being written even temporarily.
    with db.no_autoflush:
        other = db.scalar(scoped(db, identity, CalendarEvent).where(
            CalendarEvent.status == 'active', CalendarEvent.id != item.id,
            CalendarEvent.start_at < item.end_at, CalendarEvent.end_at > item.start_at).limit(1))
    if other:
        raise problem(409, 'EVENT_CONFLICT', '该时间段与已有日程重叠，请调整时间后保存')


def check_link(db, identity, event_id):
    if event_id is not None:
        resource(db, identity, CalendarEvent, event_id)


@router.get('/events')
def events(db: DB, identity: Auth, start: AwareDatetime, end: AwareDatetime,
           status: EventStatus | None = None, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=500)):
    if end <= start or (end - start).days > 370:
        raise problem(422, 'INVALID_TIME_RANGE', '请选择不超过一年的有效日期范围')
    query = scoped(db, identity, CalendarEvent).where(CalendarEvent.start_at < end, CalendarEvent.end_at > start)
    if status:
        query = query.where(CalendarEvent.status == status)
    items = db.scalars(query.order_by(CalendarEvent.start_at, CalendarEvent.id).offset(offset).limit(limit+1)).all()
    return {'items': [serialize(v) for v in items[:limit]], 'has_more': len(items) > limit}


@router.get('/events/{item_id}')
def event(item_id: UUID, db: DB, identity: Auth):
    return serialize(resource(db, identity, CalendarEvent, item_id))


@router.post('/events', status_code=201)
def create_event(body: EventCreate, request: Request, db: DB, identity: Auth):
    def write(workspace):
        item = CalendarEvent(id=uuid4(), workspace_id=workspace.id, owner_id=identity.user.id,
            **body.model_dump(), status='active', version=1)
        check_event(db, identity, item)
        db.add(item)
        audit(db, identity.user, 'event.create', workspace.id, item.id)
        db.flush()
        return serialize(item), 201
    return mutation(request, body, db, identity, write)


@router.patch('/events/{item_id}')
def update_event(item_id: UUID, body: EventPatch, request: Request, db: DB, identity: Auth):
    def write(workspace):
        item = resource(db, identity, CalendarEvent, item_id)
        check_version(item, body.version)
        for key, value in body.model_dump(exclude_unset=True, exclude={'version'}).items():
            setattr(item, key, value)
        check_event(db, identity, item)
        item.version += 1
        audit(db, identity.user, 'event.update', workspace.id, item.id)
        db.flush()
        return serialize(item), 200
    return mutation(request, body, db, identity, write)


@router.delete('/events/{item_id}')
def cancel_event(item_id: UUID, body: Deletion, request: Request, db: DB, identity: Auth):
    # Cancellation retains task links and history. It never deletes linked tasks.
    return update_event(item_id, EventPatch(version=body.version, status='cancelled'), request, db, identity)


@router.get('/tasks')
def tasks(db: DB, identity: Auth, status: TaskStatus | None = None, due_start: AwareDatetime | None = None,
          due_end: AwareDatetime | None = None, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    if due_start and due_end and due_end <= due_start:
        raise problem(422, 'INVALID_TIME_RANGE', '请选择有效截止日期范围')
    query = scoped(db, identity, Task)
    if status:
        query = query.where(Task.status == status)
    if due_start:
        query = query.where(Task.due_at >= due_start)
    if due_end:
        query = query.where(Task.due_at < due_end)
    items = db.scalars(query.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc(), Task.id).offset(offset).limit(limit+1)).all()
    return {'items': [serialize(v) for v in items[:limit]], 'has_more': len(items) > limit}


@router.get('/tasks/{item_id}')
def task(item_id: UUID, db: DB, identity: Auth):
    return serialize(resource(db, identity, Task, item_id))


@router.post('/tasks', status_code=201)
def create_task(body: TaskCreate, request: Request, db: DB, identity: Auth):
    def write(workspace):
        check_link(db, identity, body.event_id)
        item = Task(id=uuid4(), workspace_id=workspace.id, owner_id=identity.user.id, **body.model_dump(), status='pending', version=1)
        db.add(item)
        audit(db, identity.user, 'task.create', workspace.id, item.id)
        db.flush()
        return serialize(item), 201
    return mutation(request, body, db, identity, write)


@router.patch('/tasks/{item_id}')
def update_task(item_id: UUID, body: TaskPatch, request: Request, db: DB, identity: Auth):
    def write(workspace):
        item = resource(db, identity, Task, item_id)
        check_version(item, body.version)
        if body.status and body.status not in STATES[item.status]:
            raise problem(409, 'INVALID_TASK_TRANSITION', '已结束的待办请先重新打开，再修改状态')
        if 'event_id' in body.model_fields_set:
            check_link(db, identity, body.event_id)
        for key, value in body.model_dump(exclude_unset=True, exclude={'version'}).items():
            setattr(item, key, value)
        item.version += 1
        audit(db, identity.user, 'task.update', workspace.id, item.id)
        db.flush()
        return serialize(item), 200
    return mutation(request, body, db, identity, write)


@router.delete('/tasks/{item_id}')
def delete_task(item_id: UUID, body: Deletion, request: Request, db: DB, identity: Auth):
    def write(workspace):
        item = resource(db, identity, Task, item_id)
        check_version(item, body.version)
        db.delete(item)
        audit(db, identity.user, 'task.delete', workspace.id, item.id)
        return {'id': str(item_id), 'deleted': True}, 200
    return mutation(request, body, db, identity, write)
