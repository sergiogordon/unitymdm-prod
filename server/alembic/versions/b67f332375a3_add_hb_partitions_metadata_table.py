"""add_hb_partitions_metadata_table

Revision ID: b67f332375a3
Revises: 66374c55aaf6
Create Date: 2025-10-18 20:53:55.342294

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from datetime import datetime, timezone


revision: str = 'b67f332375a3'
down_revision: Union[str, None] = '66374c55aaf6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create hb_partitions metadata table to track partition lifecycle.
    Populate with existing partitions discovered from pg_class.
    """
    conn = op.get_bind()
    
    # Create metadata table
    op.create_table(
        'hb_partitions',
        sa.Column('partition_name', sa.String(), nullable=False),
        sa.Column('range_start', sa.DateTime(), nullable=False),
        sa.Column('range_end', sa.DateTime(), nullable=False),
        sa.Column('state', sa.String(), nullable=False, server_default='active'),
        sa.Column('row_count', sa.BigInteger(), nullable=True),
        sa.Column('bytes_size', sa.BigInteger(), nullable=True),
        sa.Column('checksum_sha256', sa.String(), nullable=True),
        sa.Column('archive_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('dropped_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('partition_name')
    )
    
    op.create_index('idx_hb_partition_range', 'hb_partitions', ['range_start', 'range_end'])
    op.create_index('idx_hb_partition_state', 'hb_partitions', ['state'])
    
    # Populate metadata table with existing partitions
    # Extract partition info from pg_inherits and pg_class
    conn.execute(text("""
        INSERT INTO hb_partitions (partition_name, range_start, range_end, state, created_at)
        SELECT 
            c.relname as partition_name,
            -- Parse date from partition name (device_heartbeats_YYYYMMDD)
            TO_TIMESTAMP(SUBSTRING(c.relname FROM 19), 'YYYYMMDD') as range_start,
            TO_TIMESTAMP(SUBSTRING(c.relname FROM 19), 'YYYYMMDD') + INTERVAL '1 day' as range_end,
            'active' as state,
            CURRENT_TIMESTAMP as created_at
        FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class p ON p.oid = i.inhparent
        WHERE p.relname = 'device_heartbeats'
        AND c.relname LIKE 'device_heartbeats_%'
        ORDER BY c.relname
        ON CONFLICT (partition_name) DO NOTHING
    """))
    
    # Update row counts and sizes for existing partitions
    conn.execute(text("""
        UPDATE hb_partitions
        SET 
            row_count = (
                SELECT n_tup_ins 
                FROM pg_stat_user_tables 
                WHERE schemaname = 'public' AND relname = hb_partitions.partition_name
            ),
            bytes_size = (
                SELECT pg_total_relation_size('public.' || hb_partitions.partition_name)
            )
        WHERE state = 'active'
    """))
    
    print("✓ Created hb_partitions metadata table and populated with existing partitions")


def downgrade() -> None:
    """
    Drop the partition metadata table.
    """
    op.drop_index('idx_hb_partition_state', 'hb_partitions')
    op.drop_index('idx_hb_partition_range', 'hb_partitions')
    op.drop_table('hb_partitions')
    
    print("✓ Dropped hb_partitions metadata table")
