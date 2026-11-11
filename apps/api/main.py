"""Series Sync API entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.core.config import settings
from apps.api.routers import pipeline, voices, stats

from apps.api.routers import auth
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Local demo on SQLite: create tables. Postgres deployments use `alembic upgrade head` (RLS, roles).
    if settings.ENV == "development" and settings.DATABASE_URL.startswith("sqlite"):
        from apps.db.models import Base
        from apps.db.session import engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Series Sync SaaS", version="1.0.0", docs_url="/docs", lifespan=lifespan)

@app.middleware("http")
async def limit_upload_size(request, call_next):
    """Reject oversized uploads before the multipart body is parsed and spooled to disk."""
    if request.method == "POST" and request.url.path.startswith(("/uploads", "/voices/clone")):
        from fastapi.responses import JSONResponse
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse({"detail": "Content-Length required"}, status_code=411)
        if not length.isdigit() or int(length) > settings.MAX_UPLOAD_MB * 1024 * 1024 + 1024 * 1024:
            return JSONResponse({"detail": f"File larger than {settings.MAX_UPLOAD_MB} MB"}, status_code=413)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=False,  # bearer tokens, no cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(pipeline.uploads)
app.include_router(pipeline.router)
app.include_router(voices.router)
app.include_router(stats.router)

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

app.mount("/app", StaticFiles(directory=Path(__file__).resolve().parents[1] / "web", html=True), name="web")

@app.get("/")
def root():
    return RedirectResponse(url="/app/")

@app.get("/api-info")
def api_info():
    return {"service": "Series Sync SaaS", "version": "1.0.0"}

@app.get("/healthz")
def health():
    return {"status": "ok", "version": "1.0.0"}
