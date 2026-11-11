"""add voice_profile_id to sync_jobs

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-11 10:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sync_jobs', sa.Column('voice_profile_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_sync_jobs_voice_profile', 'sync_jobs', 'voice_profiles',
        ['voice_profile_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_sync_jobs_voice_profile', 'sync_jobs', type_='foreignkey')
    op.drop_column('sync_jobs', 'voice_profile_id')
