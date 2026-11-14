import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="seriessync-test-")
os.environ.setdefault("ENV", "development")
os.environ["PROVIDER_MODE"] = "fake"
os.environ["DB_NULLPOOL"] = "1"
os.environ["STORAGE_DIR"] = os.path.join(_tmp, "storage")
# Postgres RLS tests run only when DATABASE_URL is given explicitly (CI service / local test DB).
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_tmp}/app.db")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.db.models import Base

pytest_plugins = ("pytest_asyncio",)


PG_APP = os.environ.get("PG_TEST_APP_URL")      # RLS-restricted app role (no owner rights)
PG_OWNER = os.environ.get("PG_TEST_OWNER_URL")  # only used to empty the tables between tests


@pytest_asyncio.fixture
async def session_factory():
    if PG_APP:
        from sqlalchemy import text
        owner = create_async_engine(PG_OWNER)
        async with owner.begin() as conn:
            await conn.execute(text("TRUNCATE " + ", ".join(t.name for t in Base.metadata.sorted_tables) + " CASCADE"))
        await owner.dispose()
        engine = create_async_engine(PG_APP, poolclass=__import__("sqlalchemy.pool").pool.NullPool)
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await engine.dispose()
        return
    engine = create_async_engine(f"sqlite+aiosqlite:///{tempfile.mkdtemp(dir=_tmp)}/t.db", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    import asyncio

    from apps.media import ffmpeg
    p = tmp_path_factory.mktemp("media") / "episode.mp4"
    asyncio.run(ffmpeg.synth_test_video(p, seconds=8.0))
    return p


@pytest.fixture
def client(session_factory):
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from apps.api.routers import pipeline as pipeline_router
    from apps.db.session import get_session
    from apps.services.dubbing_pipeline import DubbingPipeline

    async def _session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[pipeline_router.get_pipeline] = lambda: DubbingPipeline(session_factory)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
