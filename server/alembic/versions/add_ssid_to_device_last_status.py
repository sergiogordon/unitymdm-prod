
"""add ssid to device_last_status

Revision ID: add_ssid_to_last_status
Revises: fe5b481d1e30
Create Date: 2025-01-24 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_ssid_to_last_status'
down_revision: Union[str, None] = 'fe5b481d1e30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add ssid column to device_last_status
    op.add_column('device_last_status', sa.Column('ssid', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove ssid column
    op.drop_column('device_last_status', 'ssid')
