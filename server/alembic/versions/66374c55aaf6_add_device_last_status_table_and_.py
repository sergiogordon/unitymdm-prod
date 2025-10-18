"""add_device_last_status_table_and_partition_heartbeats

Revision ID: 66374c55aaf6
Revises: c73b10a6beaa
Create Date: 2025-10-18 20:33:51.560820

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from datetime import datetime, timedelta, timezone


revision: str = '66374c55aaf6'
down_revision: Union[str, None] = 'c73b10a6beaa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    1. Create device_last_status table for O(1) fast reads (if not exists)
    2. Convert device_heartbeats to partitioned table (daily partitions)
    3. Create initial partitions and indexes
    """
    conn = op.get_bind()
    
    # Step 1: Create device_last_status table (idempotent)
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'device_last_status'
        )
    """))
    table_exists = result.scalar()
    
    if not table_exists:
        op.create_table(
            'device_last_status',
            sa.Column('device_id', sa.String(), nullable=False),
            sa.Column('last_ts', sa.DateTime(), nullable=False),
            sa.Column('battery_pct', sa.Integer(), nullable=True),
            sa.Column('network_type', sa.String(), nullable=True),
            sa.Column('unity_running', sa.Boolean(), nullable=True),
            sa.Column('signal_dbm', sa.Integer(), nullable=True),
            sa.Column('agent_version', sa.String(), nullable=True),
            sa.Column('ip', sa.String(), nullable=True),
            sa.Column('status', sa.String(), nullable=False, server_default='ok'),
            sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
            sa.PrimaryKeyConstraint('device_id')
        )
        
        op.create_index('idx_last_status_ts', 'device_last_status', ['last_ts'])
        op.create_index('idx_last_status_offline_query', 'device_last_status', ['last_ts', 'status'])
        op.create_index('idx_last_status_unity_down', 'device_last_status', ['unity_running', 'last_ts'])
        
        # Populate device_last_status from existing device_heartbeats
        conn.execute(text("""
            INSERT INTO device_last_status (
                device_id, last_ts, battery_pct, network_type, 
                unity_running, signal_dbm, agent_version, ip, status
            )
            SELECT DISTINCT ON (device_id)
                device_id,
                ts as last_ts,
                battery_pct,
                network_type,
                unity_running,
                signal_dbm,
                agent_version,
                ip,
                status
            FROM device_heartbeats
            ORDER BY device_id, ts DESC
            ON CONFLICT (device_id) DO NOTHING
        """))
        print("✓ Created device_last_status table")
    else:
        print("✓ device_last_status table already exists")
    
    # Step 2: Check if device_heartbeats is already partitioned
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' 
            AND c.relname = 'device_heartbeats'
            AND c.relkind = 'p'
        )
    """))
    is_partitioned = result.scalar()
    
    if is_partitioned:
        print("✓ device_heartbeats is already partitioned")
        return
    
    # Step 3: Convert device_heartbeats to partitioned table
    print("→ Converting device_heartbeats to partitioned table...")
    
    # Rename the existing table
    conn.execute(text("ALTER TABLE device_heartbeats RENAME TO device_heartbeats_old"))
    
    # Create new partitioned table
    conn.execute(text("""
        CREATE TABLE device_heartbeats (
            hb_id BIGSERIAL,
            device_id VARCHAR NOT NULL,
            ts TIMESTAMP NOT NULL,
            ip VARCHAR,
            status VARCHAR NOT NULL DEFAULT 'ok',
            battery_pct INTEGER,
            plugged BOOLEAN,
            temp_c INTEGER,
            network_type VARCHAR,
            signal_dbm INTEGER,
            uptime_s INTEGER,
            ram_used_mb INTEGER,
            unity_pkg_version VARCHAR,
            unity_running BOOLEAN,
            agent_version VARCHAR,
            PRIMARY KEY (device_id, ts, hb_id)
        ) PARTITION BY RANGE (ts)
    """))
    
    # Add foreign key constraint
    conn.execute(text("""
        ALTER TABLE device_heartbeats 
        ADD CONSTRAINT device_heartbeats_device_id_fkey 
        FOREIGN KEY (device_id) REFERENCES devices(id)
    """))
    
    # Step 4: Create partitions for the last 90 days + next 14 days
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = (now + timedelta(days=14)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    current_date = start_date
    partitions_created = 0
    while current_date <= end_date:
        next_date = current_date + timedelta(days=1)
        partition_name = f"device_heartbeats_{current_date.strftime('%Y%m%d')}"
        
        conn.execute(text(f"""
            CREATE TABLE {partition_name} PARTITION OF device_heartbeats
            FOR VALUES FROM ('{current_date.isoformat()}') TO ('{next_date.isoformat()}')
        """))
        
        # Create indexes on the partition
        conn.execute(text(f"""
            CREATE INDEX idx_{partition_name}_device_ts 
            ON {partition_name} (device_id, ts DESC)
        """))
        
        # Create unique constraint for deduplication (device_id + 10-second bucket)
        conn.execute(text(f"""
            CREATE UNIQUE INDEX idx_{partition_name}_dedupe 
            ON {partition_name} (
                device_id, 
                date_trunc('minute', ts), 
                ((EXTRACT(EPOCH FROM ts)::bigint / 10) % 6)
            )
        """))
        
        partitions_created += 1
        current_date = next_date
    
    print(f"✓ Created {partitions_created} daily partitions")
    
    # Step 5: Copy data from old table to partitioned table
    print("→ Copying existing heartbeat data to partitioned table...")
    result = conn.execute(text("""
        INSERT INTO device_heartbeats 
        SELECT * FROM device_heartbeats_old
        ON CONFLICT DO NOTHING
    """))
    print(f"✓ Copied heartbeat data")
    
    # Step 6: Drop old table
    conn.execute(text("DROP TABLE device_heartbeats_old CASCADE"))
    print("✓ Dropped old table")
    
    # Step 7: Create function to auto-create partitions
    conn.execute(text("""
        CREATE OR REPLACE FUNCTION create_heartbeat_partition(partition_date DATE)
        RETURNS void AS $$
        DECLARE
            partition_name TEXT;
            start_date TIMESTAMP;
            end_date TIMESTAMP;
        BEGIN
            partition_name := 'device_heartbeats_' || to_char(partition_date, 'YYYYMMDD');
            start_date := partition_date;
            end_date := partition_date + INTERVAL '1 day';
            
            -- Check if partition already exists
            IF NOT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = partition_name
            ) THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF device_heartbeats FOR VALUES FROM (%L) TO (%L)',
                    partition_name, start_date, end_date
                );
                
                -- Create indexes
                EXECUTE format(
                    'CREATE INDEX idx_%I_device_ts ON %I (device_id, ts DESC)',
                    partition_name, partition_name
                );
                
                EXECUTE format(
                    'CREATE UNIQUE INDEX idx_%I_dedupe ON %I (device_id, date_trunc(%L, ts), ((EXTRACT(EPOCH FROM ts)::bigint / 10) %% 6))',
                    partition_name, partition_name, 'minute'
                );
                
                RAISE NOTICE 'Created partition %', partition_name;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """))
    
    print("✓ Migration complete: device_last_status table ready and device_heartbeats partitioned")


def downgrade() -> None:
    """
    Rollback: Remove partitions and device_last_status table
    """
    conn = op.get_bind()
    
    # Drop the partition creation function
    conn.execute(text("DROP FUNCTION IF EXISTS create_heartbeat_partition(DATE)"))
    
    # Check if heartbeats is partitioned
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' 
            AND c.relname = 'device_heartbeats'
            AND c.relkind = 'p'
        )
    """))
    is_partitioned = result.scalar()
    
    if is_partitioned:
        # Recreate non-partitioned table
        conn.execute(text("""
            CREATE TABLE device_heartbeats_new (
                hb_id BIGSERIAL PRIMARY KEY,
                device_id VARCHAR NOT NULL REFERENCES devices(id),
                ts TIMESTAMP NOT NULL,
                ip VARCHAR,
                status VARCHAR NOT NULL DEFAULT 'ok',
                battery_pct INTEGER,
                plugged BOOLEAN,
                temp_c INTEGER,
                network_type VARCHAR,
                signal_dbm INTEGER,
                uptime_s INTEGER,
                ram_used_mb INTEGER,
                unity_pkg_version VARCHAR,
                unity_running BOOLEAN,
                agent_version VARCHAR
            )
        """))
        
        # Copy data back
        conn.execute(text("""
            INSERT INTO device_heartbeats_new 
            SELECT * FROM device_heartbeats
        """))
        
        # Drop partitioned table
        conn.execute(text("DROP TABLE device_heartbeats CASCADE"))
        
        # Rename back
        conn.execute(text("ALTER TABLE device_heartbeats_new RENAME TO device_heartbeats"))
        
        # Recreate original indexes
        conn.execute(text("CREATE INDEX idx_heartbeat_device_ts ON device_heartbeats (device_id, ts)"))
        conn.execute(text("CREATE INDEX device_heartbeats_device_id_idx ON device_heartbeats (device_id)"))
        conn.execute(text("CREATE INDEX device_heartbeats_ts_idx ON device_heartbeats (ts)"))
    
    # Drop device_last_status table if it exists
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'device_last_status'
        )
    """))
    if result.scalar():
        op.drop_index('idx_last_status_unity_down', 'device_last_status')
        op.drop_index('idx_last_status_offline_query', 'device_last_status')
        op.drop_index('idx_last_status_ts', 'device_last_status')
        op.drop_table('device_last_status')
    
    print("✓ Rollback complete: Reverted to non-partitioned device_heartbeats")
