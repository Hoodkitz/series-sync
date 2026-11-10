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
    tenant = (await session.execute(select(TenantModel).where(TenantModel.id == req.tenant_id))).scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    db = VoiceProfileModel(
        tenant_id=req.tenant_id,
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
    return voice


@router.get("/tenant/{tenant_id}")
async def list_voices(tenant_id: UUID, current_user: User = Depends(check_permission(Permission.READ_VOICE)), session: AsyncSession = Depends(get_session)):
    stmt = select(VoiceProfileModel).where(VoiceProfileModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return VoiceListResponse(voices=[v async for v in result.scalars])
