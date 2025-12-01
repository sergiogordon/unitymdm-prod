"""add_auto_relaunch_defaults_table

Revision ID: a1b2c3d4e5f6
Revises: fe5b481d1e30
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'fe5b481d1e30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('auto_relaunch_defaults',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('package', sa.String(), nullable=False, server_default='io.unitynodes.unityapp'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_auto_relaunch_defaults_updated', 'auto_relaunch_defaults', ['updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_auto_relaunch_defaults_updated', table_name='auto_relaunch_defaults')
    op.drop_table('auto_relaunch_defaults')

