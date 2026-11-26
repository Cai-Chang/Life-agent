"""Calendar, tasks and transaction-scoped idempotency records."""
from alembic import op
import sqlalchemy as sa

revision = '0003_calendar_tasks'
down_revision = '0002_auth_personal'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('audit_logs', sa.Column('target_id', sa.Uuid(), nullable=True))
    for table in ('calendar_events', 'tasks'):
        columns = [
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('workspace_id', sa.Uuid(), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
            sa.Column('owner_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('status', sa.String(16), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        ]
        if table == 'calendar_events':
            columns += [sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
                sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
                sa.CheckConstraint('end_at > start_at', name='event_positive_duration'),
                sa.CheckConstraint("status IN ('active', 'cancelled')", name='event_status')]
        else:
            columns += [sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
                sa.Column('event_id', sa.Uuid(), sa.ForeignKey('calendar_events.id', ondelete='SET NULL'), nullable=True),
                sa.Column('priority', sa.String(16), nullable=False),
                sa.CheckConstraint("status IN ('pending', 'in_progress', 'done', 'cancelled')", name='task_status'),
                sa.CheckConstraint("priority IN ('low', 'normal', 'high')", name='task_priority')]
        op.create_table(table, *columns)
    op.create_index('ix_events_owner_start', 'calendar_events', ['workspace_id', 'owner_id', 'start_at'])
    op.create_index('ix_tasks_status_due', 'tasks', ['workspace_id', 'status', 'due_at'])
    op.create_table('operation_records',
        sa.Column('workspace_id', sa.Uuid(), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('operation_id', sa.String(128), primary_key=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade():
    op.drop_table('operation_records')
    op.drop_table('tasks')
    op.drop_table('calendar_events')
    op.drop_column('audit_logs', 'target_id')
