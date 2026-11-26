"""Personal conversations, ordered messages, durable model request leases."""
from alembic import op
import sqlalchemy as sa

revision = '0004_conversations'
down_revision = '0003_calendar_tasks'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('conversations',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('workspace_id',sa.Uuid(),sa.ForeignKey('workspaces.id',ondelete='CASCADE'),nullable=False),
        sa.Column('owner_id',sa.Uuid(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('title',sa.String(80),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('next_sequence',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index('ix_conversations_owner_updated','conversations',['workspace_id','owner_id','updated_at'])
    op.create_table('messages',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('conversation_id',sa.Uuid(),sa.ForeignKey('conversations.id',ondelete='CASCADE'),nullable=False),
        sa.Column('turn_key',sa.String(128),nullable=False),
        sa.Column('sequence',sa.Integer(),nullable=False),
        sa.Column('role',sa.String(16),nullable=False),
        sa.Column('content',sa.Text(),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('error_code',sa.String(64),nullable=True),
        sa.Column('lease_token',sa.Uuid(),nullable=True),
        sa.Column('lease_until',sa.DateTime(timezone=True),nullable=True),
        sa.Column('attempts',sa.Integer(),nullable=False),
        sa.Column('model',sa.String(128),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint('conversation_id','sequence',name='uq_message_sequence'),
        sa.UniqueConstraint('conversation_id','turn_key','role',name='uq_message_turn_role'),
        sa.CheckConstraint("role IN ('user','assistant')",name='message_role'),
        sa.CheckConstraint("status IN ('complete','pending','failed')",name='message_status'))


def downgrade():
    op.drop_table('messages')
    op.drop_table('conversations')
