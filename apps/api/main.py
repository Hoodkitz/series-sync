"""Series Sync API entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.core.config import settings
from apps.api.routers import pipeline, voices, stats

from apps.api.routers import auth
app = FastAPI(title="Series Sync SaaS", version="1.0.0", docs_url="/docs")

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

@app.get("/")
def root():
    return {"service": "Series Sync SaaS", "version": "1.0.0"}

@app.get("/healthz")
def health():
    return {"status": "ok", "version": "1.0.0"}
