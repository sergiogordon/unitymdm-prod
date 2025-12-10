"""add batch deployment tables

Revision ID: add_batch_deployment_001
Revises: add_wifi_settings_001
Create Date: 2025-12-10

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_batch_deployment_001'
down_revision = 'add_wifi_settings_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ApkDeploymentRun table
    op.execute("""
        CREATE TABLE IF NOT EXISTS apk_deployment_runs (
            id SERIAL PRIMARY KEY,
            apk_version_id INTEGER NOT NULL REFERENCES apk_versions(id),
            initiated_by VARCHAR,
            
            total_devices INTEGER NOT NULL,
            batch_size INTEGER NOT NULL DEFAULT 5,
            success_threshold INTEGER NOT NULL DEFAULT 3,
            batch_timeout_minutes INTEGER NOT NULL DEFAULT 15,
            
            status VARCHAR NOT NULL DEFAULT 'pending',
            current_batch_index INTEGER NOT NULL DEFAULT 0,
            total_batches INTEGER NOT NULL DEFAULT 0,
            
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            timeout_count INTEGER NOT NULL DEFAULT 0,
            
            started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP WITHOUT TIME ZONE
        )
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_deployment_run_status ON apk_deployment_runs(status, started_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_deployment_run_apk ON apk_deployment_runs(apk_version_id, status)")
    
    # Create ApkDeploymentBatch table
    op.execute("""
        CREATE TABLE IF NOT EXISTS apk_deployment_batches (
            id SERIAL PRIMARY KEY,
            deployment_run_id INTEGER NOT NULL REFERENCES apk_deployment_runs(id) ON DELETE CASCADE,
            batch_index INTEGER NOT NULL,
            
            status VARCHAR NOT NULL DEFAULT 'pending',
            
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            timeout_count INTEGER NOT NULL DEFAULT 0,
            devices_in_batch INTEGER NOT NULL DEFAULT 0,
            
            started_at TIMESTAMP WITHOUT TIME ZONE,
            completed_at TIMESTAMP WITHOUT TIME ZONE,
            timeout_at TIMESTAMP WITHOUT TIME ZONE,
            
            CONSTRAINT uq_run_batch UNIQUE(deployment_run_id, batch_index)
        )
    """)
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_deployment_batch_run ON apk_deployment_batches(deployment_run_id, batch_index)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_deployment_batch_status ON apk_deployment_batches(status, timeout_at)")
    
    # Add columns to ApkInstallation
    op.execute("ALTER TABLE apk_installations ADD COLUMN IF NOT EXISTS deployment_run_id INTEGER REFERENCES apk_deployment_runs(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE apk_installations ADD COLUMN IF NOT EXISTS deployment_batch_id INTEGER REFERENCES apk_deployment_batches(id) ON DELETE SET NULL")
    
    op.execute("CREATE INDEX IF NOT EXISTS idx_installation_run ON apk_installations(deployment_run_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_installation_batch ON apk_installations(deployment_batch_id, status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_installation_batch")
    op.execute("DROP INDEX IF EXISTS idx_installation_run")
    op.execute("ALTER TABLE apk_installations DROP COLUMN IF EXISTS deployment_batch_id")
    op.execute("ALTER TABLE apk_installations DROP COLUMN IF EXISTS deployment_run_id")
    
    op.execute("DROP TABLE IF EXISTS apk_deployment_batches")
    op.execute("DROP TABLE IF EXISTS apk_deployment_runs")
