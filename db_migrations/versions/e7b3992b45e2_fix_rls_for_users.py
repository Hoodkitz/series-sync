"""Fix RLS for users

Revision ID: e7b3992b45e2
Revises: 9c2411858dcf
Create Date: 2026-11-10 19:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b3992b45e2'
down_revision: Union[str, Sequence[str], None] = '9c2411858dcf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users need to be readable/writable by the app without RLS
    # to support login/registration
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY;")

def downgrade() -> None:
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY;")
