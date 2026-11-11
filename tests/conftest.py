import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="seriessync-test-")
os.environ.setdefault("ENV", "development")
os.environ["PROVIDER_MODE"] = "fake"
os.environ["STORAGE_DIR"] = os.path.join(_tmp, "storage")
# Postgres RLS tests run only when DATABASE_URL is given explicitly (CI service / local test DB).
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_tmp}/app.db")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from apps.db.models import Base  # noqa: E402

pytest_plugins = ("pytest_asyncio",)


@pytest_asyncio.fixture
async def session_factory():
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
