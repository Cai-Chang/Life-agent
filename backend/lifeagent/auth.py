"""Cookie sessions: credentials never enter browser storage or audit logs."""
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import os
import secrets
import threading
import time
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import create_engine, select, delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from lifeagent.database import database_url
from lifeagent.models import AuditLog, BrowserSession, Membership, User, Workspace

router = APIRouter(prefix='/api/v1')
hasher = PasswordHasher()
dummy_hash = hasher.hash(secrets.token_urlsafe(32))
COOKIE = 'lifeagent_session'


def problem(status: int, code: str, message: str):
    return HTTPException(status_code=status, detail={'code': code, 'message': message})


class AuthLimiter:
    """Bounded per-process throttle for a single API instance, not a shared limiter."""
    def __init__(self):
        self.entries = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, host: str):
        now = time.monotonic()
        with self.lock:
            for key in list(self.entries):
                if not self.entries[key] or self.entries[key][-1] < now - 60:
                    del self.entries[key]
            attempts = self.entries[host]
            while attempts and attempts[0] < now - 60:
                attempts.popleft()
            if len(attempts) >= 15 or len(self.entries) > 10000:
                raise problem(429, 'RATE_LIMITED', '请求过于频繁，请稍后再试')
            attempts.append(now)


def db_session():
    engine = None
    try:
        engine = create_engine(database_url(), poolclass=NullPool,
            connect_args={'connect_timeout': 3, 'options': '-c statement_timeout=5000'}, hide_parameters=True)
        with Session(engine, expire_on_commit=False) as session:
            yield session
    except SQLAlchemyError:
        raise problem(503, 'DATABASE_UNAVAILABLE', '数据库暂不可用，请稍后重试') from None
    except ValueError:
        raise problem(503, 'DATABASE_UNAVAILABLE', '数据库尚未正确配置') from None
    finally:
        if engine is not None:
            engine.dispose()


DB = Annotated[Session, Depends(db_session)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Registration(Input):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
    timezone: str = 'Asia/Shanghai'

    @field_validator('display_name')
    @classmethod
    def name(cls, value):
        if not value.strip():
            raise ValueError('昵称不能为空')
        return value.strip()

    @field_validator('timezone')
    @classmethod
    def zone(cls, value):
        try:
            if len(value) > 64:
                raise ValueError('无效时区')
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('请选择有效的 IANA 时区') from None
        return value


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileUpdate(Input):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    timezone: str | None = None

    @field_validator('display_name')
    @classmethod
    def name(cls, value):
        if value is None:
            raise ValueError('昵称不能为空')
        return Registration.name(value)

    @field_validator('timezone')
    @classmethod
    def zone(cls, value):
        if value is None:
            raise ValueError('时区不能为空')
        return Registration.zone(value)


class WorkspaceUpdate(Input):
    name: str = Field(min_length=1, max_length=80)

    @field_validator('name')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('空间名称不能为空')
        return value.strip()


@dataclass
class Identity:
    user: User
    session: BrowserSession


def current(request: Request, db: DB) -> Identity:
    token = request.cookies.get(COOKIE, '')
    if not 32 <= len(token) <= 128:
        raise problem(401, 'UNAUTHENTICATED', '请先登录')
    session = db.get(BrowserSession, sha256(token.encode()).hexdigest())
    if session is None or session.expires_at <= datetime.now(timezone.utc):
        raise problem(401, 'SESSION_EXPIRED', '登录已过期，请重新登录')
    user = db.get(User, session.user_id)
    if user is None:
        raise problem(401, 'UNAUTHENTICATED', '请重新登录')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        header = request.headers.get('X-CSRF-Token', '')
        if not hmac.compare_digest(header.encode(), session.csrf_token.encode()):
            raise problem(403, 'CSRF_REJECTED', '页面验证已失效，请刷新后再试')
    return Identity(user, session)


Auth = Annotated[Identity, Depends(current)]


def workspace_data(w: Workspace):
    return {'id': str(w.id), 'name': w.name, 'type': w.type, 'role': 'owner', 'created_at': w.created_at.isoformat()}


def owned_workspace(db: Session, user: User, workspace_id: UUID | None = None):
    query = select(Workspace).join(Membership, Membership.workspace_id == Workspace.id).where(
        Membership.user_id == user.id, Workspace.owner_id == user.id)
    if workspace_id is not None:
        query = query.where(Workspace.id == workspace_id)
    workspace = db.scalar(query)
    if workspace is None:
        raise problem(404, 'NOT_FOUND', '空间不存在或你无权访问')
    return workspace


def profile(db: Session, identity: Identity):
    user = identity.user
    return {'user': {'id': str(user.id), 'email': user.email, 'display_name': user.display_name,
            'timezone': user.timezone, 'created_at': user.created_at.isoformat()},
        'workspace': workspace_data(owned_workspace(db, user)), 'csrf_token': identity.session.csrf_token}


def issue_session(db: Session, user: User, response: Response, request: Request):
    # Rotate only the presented browser session; keep other devices signed in.
    old = request.cookies.get(COOKIE)
    if old:
        db.execute(delete(BrowserSession).where(BrowserSession.token_hash == sha256(old.encode()).hexdigest()))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    record = BrowserSession(token_hash=sha256(token.encode()).hexdigest(), user_id=user.id,
        csrf_token=csrf, expires_at=datetime.now(timezone.utc)+timedelta(days=7))
    db.add(record)
    db.commit()
    response.set_cookie(COOKIE, token, max_age=7*86400, httponly=True,
        secure=os.environ.get('APP_ENV') == 'production', samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return profile(db, Identity(user, record))


def audit(db, user, action, workspace_id=None):
    db.add(AuditLog(actor_id=user.id, workspace_id=workspace_id, action=action, outcome='success'))


@router.post('/auth/register', status_code=201)
def register(body: Registration, request: Request, response: Response, db: DB):
    request.app.state.auth_limiter.check(request.client.host if request.client else 'unknown')
    user = User(email=str(body.email).casefold(), password_hash=hasher.hash(body.password),
                display_name=body.display_name, timezone=body.timezone)
    try:
        db.add(user)
        db.flush()
        workspace = Workspace(owner_id=user.id, name='我的个人空间', type='personal')
        db.add(workspace)
        db.flush()
        db.add(Membership(workspace_id=workspace.id, user_id=user.id, role='owner'))
        audit(db, user, 'auth.register', workspace.id)
        return issue_session(db, user, response, request)
    except IntegrityError:
        db.rollback()
        raise problem(409, 'EMAIL_EXISTS', '该邮箱已注册，请直接登录') from None


@router.post('/auth/login')
def login(body: Login, request: Request, response: Response, db: DB):
    request.app.state.auth_limiter.check(request.client.host if request.client else 'unknown')
    user = db.scalar(select(User).where(User.email == str(body.email).casefold()))
    try:
        hasher.verify(user.password_hash if user else dummy_hash, body.password)
    except (VerificationError, InvalidHashError):
        raise problem(401, 'INVALID_CREDENTIALS', '邮箱或密码不正确') from None
    if user is None:
        raise problem(401, 'INVALID_CREDENTIALS', '邮箱或密码不正确')
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(body.password)
    audit(db, user, 'auth.login')
    return issue_session(db, user, response, request)


@router.post('/auth/logout', status_code=204)
def logout(response: Response, db: DB, identity: Auth):
    audit(db, identity.user, 'auth.logout')
    db.delete(identity.session)
    db.commit()
    response.delete_cookie(COOKIE, path='/', secure=os.environ.get('APP_ENV') == 'production', httponly=True, samesite='lax')


@router.get('/me')
def me(db: DB, identity: Auth):
    return profile(db, identity)


@router.patch('/me')
def update_me(body: ProfileUpdate, db: DB, identity: Auth):
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(identity.user, key, value)
    audit(db, identity.user, 'profile.update')
    db.commit()
    return profile(db, identity)


@router.get('/workspaces')
def workspaces(db: DB, identity: Auth):
    return {'items': [workspace_data(owned_workspace(db, identity.user))]}


@router.get('/workspaces/{workspace_id}')
def get_workspace(workspace_id: UUID, db: DB, identity: Auth):
    return workspace_data(owned_workspace(db, identity.user, workspace_id))


@router.patch('/workspaces/{workspace_id}')
def update_workspace(workspace_id: UUID, body: WorkspaceUpdate, db: DB, identity: Auth):
    workspace = owned_workspace(db, identity.user, workspace_id)
    workspace.name = body.name
    audit(db, identity.user, 'workspace.rename', workspace.id)
    db.commit()
    return workspace_data(workspace)
