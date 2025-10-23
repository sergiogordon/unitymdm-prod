"""add apk download optimization columns

Revision ID: add_apk_download_opt
Revises: add_bulk_delete_001
Create Date: 2025-10-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_apk_download_opt'
down_revision = 'add_bulk_delete_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add SHA-256 column to apk_versions for caching
    op.execute("ALTER TABLE apk_versions ADD COLUMN IF NOT EXISTS sha256 VARCHAR(64)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_apk_sha256 ON apk_versions(sha256)")
    
    # Add download telemetry columns to apk_installations
    op.execute("ALTER TABLE apk_installations ADD COLUMN IF NOT EXISTS download_start_time TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE apk_installations ADD COLUMN IF NOT EXISTS download_end_time TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE apk_installations ADD COLUMN IF NOT EXISTS bytes_downloaded INTEGER")
    op.execute("ALTER TABLE apk_installations ADD COLUMN IF NOT EXISTS avg_speed_kbps INTEGER")
    op.execute("ALTER TABLE apk_installations ADD COLUMN IF NOT EXISTS cache_hit BOOLEAN DEFAULT FALSE")


def downgrade() -> None:
    # Remove columns
    op.execute("DROP INDEX IF EXISTS idx_apk_sha256")
    op.execute("ALTER TABLE apk_versions DROP COLUMN IF EXISTS sha256")
    
    op.execute("ALTER TABLE apk_installations DROP COLUMN IF EXISTS download_start_time")
    op.execute("ALTER TABLE apk_installations DROP COLUMN IF EXISTS download_end_time")
    op.execute("ALTER TABLE apk_installations DROP COLUMN IF EXISTS bytes_downloaded")
    op.execute("ALTER TABLE apk_installations DROP COLUMN IF EXISTS avg_speed_kbps")
    op.execute("ALTER TABLE apk_installations DROP COLUMN IF EXISTS cache_hit")
