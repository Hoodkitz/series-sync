"""Voice profile management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from apps.api.security.auth import get_current_active_user
from apps.api.security.permissions import check_permission
from apps.core.permissions import Permission
from apps.db.models import User

from apps.api.schemas.pipeline import VoiceCreate, VoiceResponse, VoiceListResponse
from apps.db.session import get_session
from apps.db.models import VoiceProfile as VoiceProfileModel, Tenant as TenantModel

router = APIRouter(prefix="/voices", tags=["voices"])


@router.post("")
async def create_voice(req: VoiceCreate, current_user: User = Depends(check_permission(Permission.CREATE_VOICE)), session: AsyncSession = Depends(get_session)):
    if req.tenant_id is not None and req.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    db = VoiceProfileModel(
        tenant_id=current_user.tenant_id,
        speaker_name=req.speaker_name,
        voice_preset=req.voice_preset,
        language=req.language,
        reference_audio_url=req.reference_audio_url,
        embedding=req.embedding,
        is_default=req.is_default,
        consent=req.consent,
    )
    session.add(db)
    await session.commit()
    await session.refresh(db)
    return db


@router.get("/{voice_id}")
async def get_voice(voice_id: UUID, current_user: User = Depends(check_permission(Permission.READ_VOICE)), session: AsyncSession = Depends(get_session)):
    stmt = select(VoiceProfileModel).where(VoiceProfileModel.id == voice_id)
    result = await session.execute(stmt)
    voice = result.scalars().first()
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")

    if current_user and voice.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this voice profile")
    return voice


@router.get("/tenant/{tenant_id}")
async def list_voices(tenant_id: UUID, current_user: User = Depends(check_permission(Permission.READ_VOICE)), session: AsyncSession = Depends(get_session)):
    if tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    stmt = select(VoiceProfileModel).where(VoiceProfileModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return VoiceListResponse(voices=[v async for v in result.scalars])

@router.delete("/{voice_id}/consent")
async def revoke_consent(voice_id: UUID, current_user: User = Depends(check_permission(Permission.DELETE_VOICE)), session: AsyncSession = Depends(get_session)):
    stmt = select(VoiceProfileModel).where(VoiceProfileModel.id == voice_id)
    result = await session.execute(stmt)
    voice = result.scalars().first()
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")

    if current_user and voice.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this voice profile")

    # 1. We must delete any TTS artifacts from Jobs that used this voice
    from apps.db.models import SyncJob
    import os

    jobs_stmt = select(SyncJob).where(SyncJob.voice_profile_id == voice_id)
    jobs_result = await session.execute(jobs_stmt)

    for job in jobs_result.scalars():
        if job.tts_audio and os.path.exists(job.tts_audio):
            try:
                os.remove(job.tts_audio)
            except OSError:
                pass
        job.tts_audio = None

        if job.final_video and os.path.exists(job.final_video):
            try:
                os.remove(job.final_video)
            except OSError:
                pass
        job.final_video = None

        if job.output_video_url and os.path.exists(job.output_video_url):
            try:
                os.remove(job.output_video_url)
            except OSError:
                pass
        job.output_video_url = None

        # If there are other derived artifacts like final_video they might need deletion or metadata scrub
        # We'll just delete tts_audio per requirements: "all derived TTS artifacts"

    # 2. Delete the reference audio if it exists locally
    if voice.reference_audio_url and os.path.exists(voice.reference_audio_url):
        try:
            os.remove(voice.reference_audio_url)
        except OSError:
            pass

    # 3. Delete the voice profile itself
    await session.delete(voice)
    await session.commit()

    return {"status": "success", "message": "Consent revoked, profile and artifacts deleted"}
