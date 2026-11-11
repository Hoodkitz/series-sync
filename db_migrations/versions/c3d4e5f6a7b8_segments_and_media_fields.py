"""segment-based dubbing: segments, duration, background volume, title

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-11 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sync_jobs', sa.Column('segments', sa.JSON(), nullable=True))
    op.add_column('sync_jobs', sa.Column('duration_seconds', sa.Float(), nullable=True))
    op.add_column('sync_jobs', sa.Column('background_volume', sa.Float(), nullable=True))
    op.add_column('sync_jobs', sa.Column('title', sa.String(length=255), nullable=True))


def downgrade():
    for col in ('title', 'background_volume', 'duration_seconds', 'segments'):
        op.drop_column('sync_jobs', col)
