"""initial schema: users, auth, chat usage tables

Revision ID: d43e45fa5119
Revises:
Create Date: 2026-03-12 21:11:34.865658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'd43e45fa5119'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    """Check if a table already exists (shared DB may have it from another app)."""
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def upgrade() -> None:
    # Shared tables (may already exist from flyfun-weather or another app)
    if not _table_exists('users'):
        op.create_table('users',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('provider_sub', sa.String(length=256), nullable=False),
        sa.Column('email', sa.String(length=256), nullable=False),
        sa.Column('display_name', sa.String(length=256), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False),
        sa.Column('spending_limit', sa.Float(), server_default='500.0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )

    if not _table_exists('api_tokens'):
        op.create_table('api_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_api_tokens_token_hash'), 'api_tokens', ['token_hash'], unique=True)
        op.create_index(op.f('ix_api_tokens_user_id'), 'api_tokens', ['user_id'], unique=False)

    if not _table_exists('user_preferences'):
        op.create_table('user_preferences',
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('setup_completed', sa.Boolean(), nullable=False),
        sa.Column('encrypted_creds_json', sa.Text(), nullable=False),
        sa.Column('app_prefs_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id')
        )

    if not _table_exists('cost_ledger'):
        op.create_table('cost_ledger',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('service', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('cost', sa.Float(), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_cost_ledger_user_id'), 'cost_ledger', ['user_id'], unique=False)

    # App-specific tables (always new)
    if not _table_exists('chat_usage'):
        op.create_table('chat_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('thread_id', sa.String(length=64), nullable=True),
        sa.Column('persona_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_chat_usage_user_id'), 'chat_usage', ['user_id'], unique=False)

    if not _table_exists('anon_chat_usage'):
        op.create_table('anon_chat_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('anon_id', sa.String(length=64), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_anon_chat_usage_anon_id'), 'anon_chat_usage', ['anon_id'], unique=False)


def downgrade() -> None:
    # Only drop app-specific tables; shared tables are managed by other apps too
    op.drop_index(op.f('ix_anon_chat_usage_anon_id'), table_name='anon_chat_usage')
    op.drop_table('anon_chat_usage')
    op.drop_index(op.f('ix_chat_usage_user_id'), table_name='chat_usage')
    op.drop_table('chat_usage')
