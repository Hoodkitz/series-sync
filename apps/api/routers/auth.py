from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, EmailStr
from uuid import UUID, uuid4

from apps.db.session import get_session, set_login_email, set_tenant_context
from apps.db.models import User, Tenant
from apps.api.security.auth import verify_password, get_password_hash, create_access_token, get_current_active_user

router = APIRouter(prefix="/auth", tags=["auth"])

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    tenant_name: str | None = None  # a registration always creates its own tenant (owner = admin)

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    tenant_id: UUID
    role: str
    is_active: bool

    class Config:
        from_attributes = True

@router.post("/register", response_model=UserResponse)
async def register(user_in: UserCreate, session: AsyncSession = Depends(get_session)):
    """Self-registration opens a NEW tenant; the registering user becomes its admin.
    Joining an existing tenant is an admin action, never a client-chosen tenant_id/role."""
    if len(user_in.password) < 10:
        raise HTTPException(status_code=422, detail="Password must have at least 10 characters")
    await set_login_email(session, user_in.email)  # RLS: the duplicate check may see exactly this e-mail's row
    result = await session.execute(select(User).where(User.email == user_in.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
    tenant = Tenant(id=uuid4(), name=user_in.tenant_name or f"{user_in.email.split('@')[0]}'s workspace")
    await set_tenant_context(session, tenant.id)  # RLS: tenant + first user are written under the new tenant
    session.add(tenant)
    await session.flush()
    db_user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        tenant_id=tenant.id,
        role="admin",
    )
    session.add(db_user)
    await session.commit()
    return UserResponse(id=db_user.id, email=db_user.email, tenant_id=tenant.id, role=db_user.role,
                        is_active=True)

@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)):
    await set_login_email(session, form_data.username)  # RLS: only this e-mail's row is visible for the lookup
    result = await session.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id), "tenant_id": str(user.tenant_id), "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user
