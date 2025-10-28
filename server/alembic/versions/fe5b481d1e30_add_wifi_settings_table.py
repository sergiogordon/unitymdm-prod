"""add_wifi_settings_table

Revision ID: fe5b481d1e30
Revises: add_apk_download_opt
Create Date: 2025-10-28 02:09:07.102729

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe5b481d1e30'
down_revision: Union[str, None] = 'add_apk_download_opt'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('wifi_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ssid', sa.String(), nullable=False),
        sa.Column('password', sa.String(), nullable=False),
        sa.Column('security_type', sa.String(), nullable=False, server_default='wpa2'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_wifi_enabled', 'wifi_settings', ['enabled'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_wifi_enabled', table_name='wifi_settings')
    op.drop_table('wifi_settings')
