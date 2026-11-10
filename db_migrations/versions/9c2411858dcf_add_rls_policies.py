"""Add RLS policies

Revision ID: 9c2411858dcf
Revises: f52812efa2e2
Create Date: 2026-11-10 19:23:25.423348

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c2411858dcf'
down_revision: Union[str, Sequence[str], None] = 'f52812efa2e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable RLS
    op.execute("ALTER TABLE sync_jobs ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE voice_profiles ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")

    # Create policies
    op.execute(
        "CREATE POLICY tenant_isolation_policy ON sync_jobs "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )
    op.execute(
        "CREATE POLICY tenant_isolation_policy ON voice_profiles "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )
    op.execute(
        "CREATE POLICY tenant_isolation_policy ON users "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid);"
    )

    # Force RLS
    op.execute("ALTER TABLE sync_jobs FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE voice_profiles FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY;")

def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON sync_jobs;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON voice_profiles;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON users;")

    op.execute("ALTER TABLE sync_jobs DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE voice_profiles DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY;")
