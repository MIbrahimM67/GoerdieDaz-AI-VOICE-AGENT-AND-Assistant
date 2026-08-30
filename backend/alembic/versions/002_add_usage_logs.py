"""002 — Add usage_logs table

Revision ID: 002
Revises: 001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'usage_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('service', sa.String(64), nullable=False, index=True),
        sa.Column('operation', sa.String(64), nullable=False),
        sa.Column('tokens_in', sa.Integer, nullable=False, server_default='0'),
        sa.Column('tokens_out', sa.Integer, nullable=False, server_default='0'),
        sa.Column('characters', sa.Integer, nullable=False, server_default='0'),
        sa.Column('duration_seconds', sa.Float, nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Float, nullable=False, server_default='0'),
        sa.Column('metadata_json', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, index=True,
                  server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('usage_logs')
