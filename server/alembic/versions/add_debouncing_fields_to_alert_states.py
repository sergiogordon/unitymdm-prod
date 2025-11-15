"""add_debouncing_fields_to_alert_states

Revision ID: debounce_alert_001
Revises: fe5b481d1e30
Create Date: 2025-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'debounce_alert_001'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add debouncing fields to alert_states table
    op.add_column('alert_states', sa.Column('condition_started_at', sa.DateTime(), nullable=True))
    op.add_column('alert_states', sa.Column('condition_cleared_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('alert_states', 'condition_cleared_at')
    op.drop_column('alert_states', 'condition_started_at')
