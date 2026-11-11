"""normalize RLS policies: NULLIF-safe tenant setting, WITH CHECK everywhere, no open insert holes

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-11 19:40:00

- current_setting(...)::uuid raised "invalid input syntax for type uuid" whenever a pooled connection had an
  empty (reset) setting, e.g. on login -> intermittent 500s. NULLIF turns that into "no rows".
- sync_jobs/voice_profiles had no WITH CHECK (a tenant could write rows for another tenant id).
- Registration no longer needs open INSERT policies: the API sets the new tenant as context before inserting.
"""
from alembic import op

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None

CUR = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"
LOGIN = "NULLIF(current_setting('app.login_email', true), '')"
OLD = {
    "tenants": ["tenants_own", "tenants_register", "tenant_isolation_policy"],
    "users": ["users_tenant", "users_login", "users_register", "tenant_isolation_policy"],
    "sync_jobs": ["tenant_isolation_policy"],
    "voice_profiles": ["tenant_isolation_policy"],
}


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, names in OLD.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for name in names:
            op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
    op.execute(f"CREATE POLICY tenants_own ON tenants FOR ALL USING (id = {CUR}) WITH CHECK (id = {CUR})")
    op.execute(f"CREATE POLICY users_tenant ON users FOR ALL USING (tenant_id = {CUR}) WITH CHECK (tenant_id = {CUR})")
    op.execute(f"CREATE POLICY users_login ON users FOR SELECT USING (email = {LOGIN})")
    for table in ("sync_jobs", "voice_profiles"):
        op.execute(f"CREATE POLICY tenant_isolation_policy ON {table} FOR ALL "
                   f"USING (tenant_id = {CUR}) WITH CHECK (tenant_id = {CUR})")


def downgrade() -> None:
    pass  # policies are only tightened; the previous set had known holes and is not restored
