"""Add scope and last_used_at to enrollment_tokens, CI metadata to apk_versions

Revision ID: a43a2b52588a
Revises: 7ac6ecbe4e31
Create Date: 2025-10-18 13:39:01.917713

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a43a2b52588a'
down_revision: Union[str, None] = '7ac6ecbe4e31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to enrollment_tokens
    op.add_column('enrollment_tokens', sa.Column('scope', sa.String(), nullable=False, server_default='register'))
    op.add_column('enrollment_tokens', sa.Column('last_used_at', sa.DateTime(), nullable=True))
    op.create_index('idx_enrollment_issued_by', 'enrollment_tokens', ['issued_by', 'issued_at'])
    op.create_index(op.f('ix_enrollment_tokens_alias'), 'enrollment_tokens', ['alias'])
    op.create_unique_constraint('uq_enrollment_token_hash', 'enrollment_tokens', ['token_hash'])
    
    # Add CI metadata columns to apk_versions
    op.add_column('apk_versions', sa.Column('package_name', sa.String(), nullable=False, server_default='com.example.app'))
    op.add_column('apk_versions', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('apk_versions', sa.Column('build_type', sa.String(), nullable=True))
    op.add_column('apk_versions', sa.Column('ci_run_id', sa.String(), nullable=True))
    op.add_column('apk_versions', sa.Column('git_sha', sa.String(), nullable=True))
    op.add_column('apk_versions', sa.Column('signer_fingerprint', sa.String(), nullable=True))
    op.add_column('apk_versions', sa.Column('storage_url', sa.Text(), nullable=True))
    op.create_index('idx_apk_build_type', 'apk_versions', ['version_code', 'build_type'])
    op.create_index('idx_apk_version_lookup', 'apk_versions', ['package_name', 'version_code'])


def downgrade() -> None:
    # Remove indexes and columns from apk_versions
    op.drop_index('idx_apk_version_lookup', table_name='apk_versions')
    op.drop_index('idx_apk_build_type', table_name='apk_versions')
    op.drop_column('apk_versions', 'storage_url')
    op.drop_column('apk_versions', 'signer_fingerprint')
    op.drop_column('apk_versions', 'git_sha')
    op.drop_column('apk_versions', 'ci_run_id')
    op.drop_column('apk_versions', 'build_type')
    op.drop_column('apk_versions', 'notes')
    op.drop_column('apk_versions', 'package_name')
    
    # Remove indexes and columns from enrollment_tokens
    op.drop_constraint('uq_enrollment_token_hash', 'enrollment_tokens', type_='unique')
    op.drop_index(op.f('ix_enrollment_tokens_alias'), table_name='enrollment_tokens')
    op.drop_index('idx_enrollment_issued_by', table_name='enrollment_tokens')
    op.drop_column('enrollment_tokens', 'last_used_at')
    op.drop_column('enrollment_tokens', 'scope')
