"""Series Sync API."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.api.routers.jobs import router as jobs_router

app = FastAPI(title="Series Sync SaaS", version="1.0.0")

app.include_router(jobs_router)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def root():
    return {"service": "Series Sync SaaS", "version": "1.0.0"}

@app.get("/healthz")
def health():
    return {"status": "ok"}
