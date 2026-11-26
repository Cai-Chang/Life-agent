"""Personal accounts, workspace ownership, and revocable browser sessions."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func, Integer, Text, Index, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64), default='Asia/Shanghai')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Workspace(Base):
    __tablename__ = 'workspaces'
    __table_args__ = (CheckConstraint("type = 'personal'", name='personal_workspace_only'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    type: Mapped[str] = mapped_column(String(16), default='personal')
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = 'memberships'
    __table_args__ = (CheckConstraint("role = 'owner'", name='personal_owner_role'),)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default='owner')


class BrowserSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    workspace_id: Mapped[UUID | None] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=True)
    target_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(16), default='success')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarEvent(Base):
    __tablename__ = 'calendar_events'
    __table_args__ = (
        CheckConstraint('end_at > start_at', name='event_positive_duration'),
        CheckConstraint("status IN ('active', 'cancelled')", name='event_status'),
        Index('ix_events_owner_start', 'workspace_id', 'owner_id', 'start_at'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default='active')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = 'tasks'
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'in_progress', 'done', 'cancelled')", name='task_status'),
        CheckConstraint("priority IN ('low', 'normal', 'high')", name='task_priority'),
        Index('ix_tasks_status_due', 'workspace_id', 'status', 'due_at'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    event_id: Mapped[UUID | None] = mapped_column(ForeignKey('calendar_events.id', ondelete='SET NULL'), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default='pending')
    priority: Mapped[str] = mapped_column(String(16), default='normal')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OperationRecord(Base):
    __tablename__ = 'operation_records'
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = 'conversations'
    __table_args__ = (Index('ix_conversations_owner_updated', 'workspace_id', 'owner_id', 'updated_at'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    title: Mapped[str] = mapped_column(String(80), default='新对话')
    version: Mapped[int] = mapped_column(Integer, default=1)
    next_sequence: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        UniqueConstraint('conversation_id', 'sequence', name='uq_message_sequence'),
        UniqueConstraint('conversation_id', 'turn_key', 'role', name='uq_message_turn_role'),
        CheckConstraint("role IN ('user','assistant')", name='message_role'),
        CheckConstraint("status IN ('complete','pending','failed')", name='message_status'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'))
    turn_key: Mapped[str] = mapped_column(String(128))
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(16), default='complete')
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    model: Mapped[str] = mapped_column(String(128), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
