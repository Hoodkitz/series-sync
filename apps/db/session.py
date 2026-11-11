"""Database session."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from apps.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id) -> None:
    """Transaction-local RLS context (no-op on SQLite used in unit tests)."""
    if session.bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text
    await session.execute(text("SELECT set_config('app.current_tenant', :tid, true)"), {"tid": str(tenant_id)})
