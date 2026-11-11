"""users back under FORCE RLS (login/registration via narrow policies); idempotency key on sync_jobs.

Revision ID: a1b2c3d4e5f6
Revises: e7b3992b45e2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e7b3992b45e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users: tenant-scoped like everything else, plus two narrow holes for login and self-registration.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON users;")
    op.execute("CREATE POLICY users_tenant ON users FOR ALL "
               "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
               "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);")
    # login: only the row whose e-mail the request is authenticating (set per transaction, before the lookup)
    op.execute("CREATE POLICY users_login ON users FOR SELECT "
               "USING (email = current_setting('app.login_email', true));")
    # self-registration creates a brand-new tenant and its first user before any tenant context exists
    op.execute("CREATE POLICY users_register ON users FOR INSERT WITH CHECK (true);")
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY;")
    op.execute("CREATE POLICY tenants_own ON tenants FOR ALL "
               "USING (id = current_setting('app.current_tenant', true)::uuid) "
               "WITH CHECK (id = current_setting('app.current_tenant', true)::uuid);")
    op.execute("CREATE POLICY tenants_register ON tenants FOR INSERT WITH CHECK (true);")
    op.add_column("sync_jobs", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_sync_jobs_tenant_idem", "sync_jobs", ["tenant_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_sync_jobs_tenant_idem", "sync_jobs", type_="unique")
    op.drop_column("sync_jobs", "idempotency_key")
    op.execute("DROP POLICY IF EXISTS tenants_register ON tenants;")
    op.execute("DROP POLICY IF EXISTS tenants_own ON tenants;")
    op.execute("ALTER TABLE tenants NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS users_register ON users;")
    op.execute("DROP POLICY IF EXISTS users_login ON users;")
    op.execute("DROP POLICY IF EXISTS users_tenant ON users;")
    op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY;")
