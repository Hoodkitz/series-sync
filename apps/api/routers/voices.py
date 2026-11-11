"""Voice profiles: stock voices by provider id, or consented voice clones from a reference recording."""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas.pipeline import VoiceCreate, VoiceListResponse, VoiceResponse
from apps.api.security.permissions import check_permission
from apps.core.permissions import Permission
from apps.db.models import SyncJob, User, VoiceProfile
from apps.db.session import get_session
from apps.media import ffmpeg, storage
from apps.services.providers import ProviderError, default_providers

log = logging.getLogger("seriessync.voices")
router = APIRouter(prefix="/voices", tags=["voices"])
MAX_SAMPLE_MB = 25


def _out(v: VoiceProfile) -> VoiceResponse:
    r = VoiceResponse.model_validate(v)
    r.cloned = bool(v.reference_audio_url)
    return r


async def _voice(session: AsyncSession, voice_id: UUID, user: User) -> VoiceProfile:
    v = (await session.execute(select(VoiceProfile).where(VoiceProfile.id == voice_id,
                                                          VoiceProfile.tenant_id == user.tenant_id))).scalars().first()
    if not v:
        raise HTTPException(404, "Voice not found")
    return v


@router.post("", response_model=VoiceResponse, status_code=201)
async def create_voice(req: VoiceCreate, user: User = Depends(check_permission(Permission.CREATE_VOICE)),
                       session: AsyncSession = Depends(get_session)):
    v = VoiceProfile(tenant_id=user.tenant_id, speaker_name=req.speaker_name, voice_preset=req.voice_preset,
                     language=req.language, reference_audio_url="", is_default=req.is_default, consent=req.consent)
    session.add(v)
    await session.commit()
    await session.refresh(v)
    return _out(v)


@router.post("/clone", response_model=VoiceResponse, status_code=201)
async def clone_voice(speaker_name: str = Form(..., min_length=1, max_length=255),
                      consent: bool = Form(...), language: str = Form("de", pattern=r"^[a-z]{2}$"),
                      sample: UploadFile = File(...),
                      user: User = Depends(check_permission(Permission.CREATE_VOICE)),
                      session: AsyncSession = Depends(get_session)):
    """Clone a voice. Requires documented consent of the speaker (GDPR Art. 9 biometric data, EU AI Act Art. 50)."""
    if not consent:
        raise HTTPException(422, "Voice cloning requires the speaker's documented consent")
    ext = Path(sample.filename or "").suffix.lower()
    if ext not in storage.ALLOWED_AUDIO_EXT:
        raise HTTPException(415, "Unsupported audio type")
    data = await sample.read(MAX_SAMPLE_MB * 1024 * 1024 + 1)
    if len(data) > MAX_SAMPLE_MB * 1024 * 1024:
        raise HTTPException(413, f"Sample larger than {MAX_SAMPLE_MB} MB")
    dst = storage.voices_dir(user.tenant_id) / f"{uuid4()}{ext}"
    dst.write_bytes(data)
    try:
        info = await ffmpeg.media_info(dst)
        if not info["has_audio"] or info["duration"] < 10:
            raise HTTPException(422, "Sample must contain at least 10 seconds of clear speech")
        voice_id = await default_providers().cloner.clone(speaker_name, dst)
    except ffmpeg.MediaError:
        dst.unlink(missing_ok=True)
        raise HTTPException(422, "Sample is not a readable audio file")
    except ProviderError as e:
        dst.unlink(missing_ok=True)
        raise HTTPException(502, f"Voice cloning failed: {e}")
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    v = VoiceProfile(tenant_id=user.tenant_id, speaker_name=speaker_name, voice_preset=voice_id, language=language,
                     reference_audio_url=str(dst), consent=True)
    session.add(v)
    await session.commit()
    await session.refresh(v)
    return _out(v)


@router.get("", response_model=VoiceListResponse)
async def list_voices(user: User = Depends(check_permission(Permission.READ_VOICE)),
                      session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(VoiceProfile).where(VoiceProfile.tenant_id == user.tenant_id)
                                  .order_by(VoiceProfile.created_at))).scalars().all()
    return VoiceListResponse(voices=[_out(v) for v in rows])


@router.get("/{voice_id}", response_model=VoiceResponse)
async def get_voice(voice_id: UUID, user: User = Depends(check_permission(Permission.READ_VOICE)),
                    session: AsyncSession = Depends(get_session)):
    return _out(await _voice(session, voice_id, user))


@router.delete("/{voice_id}/consent")
async def revoke_consent(voice_id: UUID, user: User = Depends(check_permission(Permission.DELETE_VOICE)),
                         session: AsyncSession = Depends(get_session)):
    """Consent withdrawn: delete the voice, its reference recording, the provider clone and every dub made with it.

    Stock voices carry no personal data: they are only removed from the list; existing dubs stay untouched."""
    voice = await _voice(session, voice_id, user)
    if not voice.reference_audio_url:
        jobs = (await session.execute(select(SyncJob).where(SyncJob.voice_profile_id == voice.id,
                                                            SyncJob.tenant_id == user.tenant_id))).scalars().all()
        for job in jobs:
            job.voice_profile_id = None
        await session.delete(voice)
        await session.commit()
        return {"status": "deleted", "jobs_affected": 0}
    jobs = (await session.execute(select(SyncJob).where(SyncJob.voice_profile_id == voice.id,
                                                        SyncJob.tenant_id == user.tenant_id))).scalars().all()
    for job in jobs:
        storage.delete_job_files(job.tenant_id, job.id)
        job.tts_audio = job.final_video = job.output_video_url = None
        job.segments = [{k: v for k, v in s.items() if k in ("start", "end", "text", "translation")}
                        for s in (job.segments or [])]
        job.voice_profile_id = None
        job.status = "failed"
        job.errors = (job.errors or []) + ["voice consent revoked: dub deleted"]
    ref = storage.inside_tenant(user.tenant_id, voice.reference_audio_url)
    if ref and ref.exists():
        ref.unlink()
    if voice.reference_audio_url:  # only clones live at the provider; stock voices are shared and must stay
        try:
            await default_providers().cloner.delete(voice.voice_preset)
        except ProviderError as e:  # keep going: local data is gone; provider deletion is logged for follow-up
            log.error("provider voice %s not deleted: %s", voice.voice_preset, e)
    await session.delete(voice)
    await session.commit()
    return {"status": "deleted", "jobs_affected": len(jobs)}
