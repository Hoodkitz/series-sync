import pytest_asyncio
pytest_plugins = ("pytest_asyncio",)
import pytest
import asyncio
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from apps.db.models import Base, Tenant, SyncJob
from apps.core.config import settings

@pytest_asyncio.fixture
async def pg_session_factory():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    # We assume schema is already created by alembic
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()

@pytest.mark.asyncio
async def test_tenant_isolation(pg_session_factory):
    tenant1_id = uuid4()
    tenant2_id = uuid4()
    job1_id = uuid4()
    job2_id = uuid4()

    async with pg_session_factory() as session:
        # We need a superuser or bypass RLS to setup test data,
        # or we just rely on standard insert (RLS applies mostly to SELECT/UPDATE/DELETE if policies are strictly defined,
        # but our policy might affect INSERT too. In Postgres, by default, table owner bypasses RLS unless FORCE ROW LEVEL SECURITY is set.
        # Since we use the app user, let's set current_tenant before insert for tenant1
        await session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant1_id)})

        tenant1 = Tenant(id=tenant1_id, name="T1")
        session.add(tenant1)
        job1 = SyncJob(id=job1_id, tenant_id=tenant1_id, source_video_url="v1", rights=True)
        session.add(job1)

        await session.commit()

    async with pg_session_factory() as session:
        await session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant2_id)})
        tenant2 = Tenant(id=tenant2_id, name="T2")
        session.add(tenant2)
        job2 = SyncJob(id=job2_id, tenant_id=tenant2_id, source_video_url="v2", rights=True)
        session.add(job2)

        await session.commit()

    # Now verify isolation
    async with pg_session_factory() as session:
        # Act as Tenant 1
        await session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant1_id)})

        from sqlalchemy.future import select
        result = await session.execute(select(SyncJob))
        jobs = result.scalars().all()

        assert len(jobs) == 1
        assert jobs[0].id == job1_id

        # Act as Tenant 2
        await session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant2_id)})
        result = await session.execute(select(SyncJob))
        jobs = result.scalars().all()

        assert len(jobs) == 1
        assert jobs[0].id == job2_id
