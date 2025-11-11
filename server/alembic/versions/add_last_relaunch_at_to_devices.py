"""add_last_relaunch_at_to_devices

Revision ID: add_last_relaunch_at
Revises: 66374c55aaf6
Create Date: 2025-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_last_relaunch_at'
down_revision: Union[str, None] = '66374c55aaf6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('devices', sa.Column('last_relaunch_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('devices', 'last_relaunch_at')
