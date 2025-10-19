"""add bulk delete support

Revision ID: add_bulk_delete_001
Revises: b67f332375a3
Create Date: 2025-01-18 12:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_bulk_delete_001'
down_revision = 'b67f332375a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add token_revoked_at column to devices table
    op.add_column('devices', sa.Column('token_revoked_at', sa.DateTime(), nullable=True))
    op.create_index('idx_device_token_revoked', 'devices', ['token_revoked_at'], unique=False)
    
    # Create device_selections table
    op.create_table(
        'device_selections',
        sa.Column('selection_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('filter_json', sa.Text(), nullable=True),
        sa.Column('total_count', sa.Integer(), nullable=False),
        sa.Column('device_ids_json', sa.Text(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('selection_id')
    )
    op.create_index('idx_selection_expires', 'device_selections', ['expires_at'], unique=False)
    op.create_index('idx_selection_created', 'device_selections', ['created_at'], unique=False)


def downgrade() -> None:
    # Drop device_selections table
    op.drop_index('idx_selection_created', table_name='device_selections')
    op.drop_index('idx_selection_expires', table_name='device_selections')
    op.drop_table('device_selections')
    
    # Remove token_revoked_at column from devices
    op.drop_index('idx_device_token_revoked', table_name='devices')
    op.drop_column('devices', 'token_revoked_at')
