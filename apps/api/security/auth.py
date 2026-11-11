from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import sqlalchemy as sa
from uuid import UUID

from apps.core.config import settings
from apps.db.session import get_session
from apps.db.models import User, Tenant

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_session)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = UUID(str(payload.get("sub")))
        tenant_claim = UUID(str(payload.get("tenant_id")))
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    # RLS context from the signed claim first; the row must then also belong to that tenant.
    await session.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant_id, true)") if session.bind.dialect.name == "postgresql"
        else sa.text("SELECT 1"), {"tenant_id": str(tenant_claim)} if session.bind.dialect.name == "postgresql" else {})
    result = await session.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_claim))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception

    # Set the current tenant for RLS in this session
    # SET LOCAL cannot take bind parameters; set_config(..., is_local=true) is transaction-scoped
    await session.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
        {"tenant_id": str(user.tenant_id)}
    )

    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
