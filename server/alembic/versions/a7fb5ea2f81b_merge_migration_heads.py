"""merge_migration_heads

Revision ID: a7fb5ea2f81b
Revises: d1e2f3a4b5c6, add_ssid_to_last_status
Create Date: 2025-11-26 19:23:26.594499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7fb5ea2f81b'
down_revision: Union[str, None] = ('d1e2f3a4b5c6', 'add_ssid_to_last_status')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
