"""add_discord_settings_table

Revision ID: d1e2f3a4b5c6
Revises: a1b2c3d4e5f6
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'discord_settings' not in inspector.get_table_names():
        op.create_table('discord_settings',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id')
        )
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('discord_settings')]
    if 'idx_discord_settings_updated' not in existing_indexes:
        op.create_index('idx_discord_settings_updated', 'discord_settings', ['updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_discord_settings_updated', table_name='discord_settings')
    op.drop_table('discord_settings')

