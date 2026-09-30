import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.core.security import hash_password, verify_password, create_access_token, decode_token
from app.models.user import UserModel

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class UserCreate(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    password: str
    role: str = "viewer"


class UserOut(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    last_login_at: Optional[str]
    created_at: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    result = await db.execute(select(UserModel).where(UserModel.username == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_role(*roles: str):
    async def checker(user: UserModel = Depends(get_current_user)) -> UserModel:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(roles)}")
        return user
    return checker


@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserModel).where(UserModel.username == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    user.last_login_at = datetime.utcnow()
    token = create_access_token(subject=user.username, role=user.role)
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}


@router.get("/me")
async def get_me(user: UserModel = Depends(get_current_user)):
    return _user_out(user)


@router.post("/logout")
async def logout():
    return {"message": "Logged out"}


@router.get("/users")
async def list_users(
    user: UserModel = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserModel))
    users = result.scalars().all()
    return [_user_out(u) for u in users]


@router.post("/users", status_code=201)
async def create_user(
    body: UserCreate,
    user: UserModel = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(UserModel).where(UserModel.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Username already exists")

    new_user = UserModel(
        id=str(uuid.uuid4()),
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.add(new_user)
    await db.flush()
    return _user_out(new_user)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: dict,
    current_user: UserModel = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "User not found")
    allowed = {"full_name", "email", "role", "is_active"}
    for k, v in body.items():
        if k in allowed:
            setattr(target, k, v)
    if "password" in body:
        target.hashed_password = hash_password(body["password"])
    return _user_out(target)


@router.post("/change-password")
async def change_password(
    body: PasswordChange,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    return {"message": "Password updated"}


async def ensure_default_admin():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(UserModel).where(UserModel.username == "admin"))
        if not result.scalar_one_or_none():
            admin = UserModel(
                id=str(uuid.uuid4()),
                username="admin",
                email="admin@gana.local",
                full_name="Administrator",
                hashed_password=hash_password("admin123"),
                role="admin",
            )
            db.add(admin)
            await db.commit()


def _user_out(u: UserModel) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }
