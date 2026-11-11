"""Tenant-scoped file storage on local disk.

Every path handed to ffmpeg or returned for download is derived here from server-generated UUIDs; no client-supplied
path or URL is ever opened, which closes local-file-read and SSRF holes.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from apps.core.config import settings

ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
ALLOWED_AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}
UPLOAD_PREFIX = "upload:"


def root() -> Path:
    p = Path(settings.STORAGE_DIR).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def tenant_dir(tenant_id: UUID | str) -> Path:
    p = root() / str(UUID(str(tenant_id)))
    p.mkdir(parents=True, exist_ok=True)
    return p


def uploads_dir(tenant_id: UUID | str) -> Path:
    p = tenant_dir(tenant_id) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def job_dir(tenant_id: UUID | str, job_id: UUID | str) -> Path:
    p = tenant_dir(tenant_id) / "jobs" / str(UUID(str(job_id)))
    p.mkdir(parents=True, exist_ok=True)
    return p


def voices_dir(tenant_id: UUID | str) -> Path:
    p = tenant_dir(tenant_id) / "voices"
    p.mkdir(parents=True, exist_ok=True)
    return p


def upload_path(tenant_id: UUID | str, upload_id: UUID | str) -> Path | None:
    """Resolve an upload id to its file, only inside this tenant's upload directory."""
    uid = str(UUID(str(upload_id)))
    for p in uploads_dir(tenant_id).glob(f"{uid}.*"):
        if p.is_file():
            return p
    return None


def resolve_source(tenant_id: UUID | str, source: str) -> Path | None:
    if not source.startswith(UPLOAD_PREFIX):
        return None
    try:
        return upload_path(tenant_id, source[len(UPLOAD_PREFIX):])
    except ValueError:
        return None


def inside_tenant(tenant_id: UUID | str, path: str | Path | None) -> Path | None:
    """Return the path only if it lies inside the tenant's storage (guards every delete/download)."""
    if not path:
        return None
    p = Path(path).resolve()
    base = tenant_dir(tenant_id)
    try:
        p.relative_to(base)
    except ValueError:
        return None
    return p


def delete_job_files(tenant_id: UUID | str, job_id: UUID | str) -> None:
    d = tenant_dir(tenant_id) / "jobs" / str(UUID(str(job_id)))
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
