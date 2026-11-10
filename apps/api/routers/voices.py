"""Voice profile management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from apps.api.schemas.pipeline import VoiceCreate, VoiceResponse, VoiceListResponse
from apps.db.session import get_session
from apps.db.models import VoiceProfile as VoiceProfileModel, Tenant as TenantModel

router = APIRouter(prefix="/voices", tags=["voices"])


@router.post("")
async def create_voice(req: VoiceCreate, session: AsyncSession = Depends(get_session)):
    tenant = (await session.execute(select(TenantModel).where(TenantModel.id == req.tenant_id))).scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    db = VoiceProfileModel(
        id=UUID(req.tenant_id.hex + "_voice_" + UUID(int=0).hex),
        tenant_id=req.tenant_id,
        speaker_name=req.speaker_name,
        voice_preset=req.voice_preset,
        language=req.language,
        reference_audio_url=req.reference_audio_url,
        embedding=req.embedding,
        is_default=req.is_default,
    )
    session.add(db)
    await session.commit()
    return db


@router.get("/{voice_id}")
async def get_voice(voice_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(VoiceProfileModel).where(VoiceProfileModel.id == voice_id)
    result = await session.execute(stmt)
    voice = result.scalars().first()
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    return voice


@router.get("/tenant/{tenant_id}")
async def list_voices(tenant_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(VoiceProfileModel).where(VoiceProfileModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return VoiceListResponse(voices=[v async for v in result.scalars])
