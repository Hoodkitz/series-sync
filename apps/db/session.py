"""Database session."""
import os

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.pool import NullPool
from apps.core.config import settings

# DB_NULLPOOL=1 (tests): the app is driven from several event loops; pooled asyncpg connections must not outlive them.
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True,
                             **({"poolclass": NullPool} if os.environ.get("DB_NULLPOOL") == "1" else {}))
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


_SET_TENANT = text("SELECT set_config('app.current_tenant', :v, true)")
_SET_LOGIN = text("SELECT set_config('app.login_email', :v, true)")


@event.listens_for(Session, "after_begin")
def _apply_rls_context(session: Session, transaction, connection) -> None:
    """Re-apply the RLS context in EVERY transaction of a session.

    set_config(..., true) is transaction-local (no leak through the pool), so without this hook everything after the
    first commit() - e.g. every later pipeline stage - would run without tenant context on Postgres.
    """
    if connection.dialect.name != "postgresql":
        return
    if session.info.get("tenant_id"):
        connection.execute(_SET_TENANT, {"v": session.info["tenant_id"]})
    if session.info.get("login_email"):
        connection.execute(_SET_LOGIN, {"v": session.info["login_email"]})


async def set_tenant_context(session: AsyncSession, tenant_id) -> None:
    """RLS tenant for this session: applies to the current and all following transactions."""
    session.info["tenant_id"] = str(tenant_id)
    if session.bind.dialect.name == "postgresql" and session.in_transaction():
        await session.execute(_SET_TENANT, {"v": str(tenant_id)})


async def set_login_email(session: AsyncSession, email: str) -> None:
    """Opens the narrow users_login RLS hole for this session's login lookup (no-op on SQLite)."""
    session.info["login_email"] = email
    if session.bind.dialect.name == "postgresql" and session.in_transaction():
        await session.execute(_SET_LOGIN, {"v": email})
