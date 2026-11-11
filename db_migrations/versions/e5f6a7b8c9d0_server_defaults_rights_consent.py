"""server defaults for sync_jobs.rights and voice_profiles.consent (match the models)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-11 22:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('sync_jobs', 'rights', server_default=sa.false())
    op.alter_column('voice_profiles', 'consent', server_default=sa.false())


def downgrade():
    op.alter_column('sync_jobs', 'rights', server_default=None)
    op.alter_column('voice_profiles', 'consent', server_default=None)
