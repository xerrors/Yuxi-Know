"""用户级配置与凭据路由"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.api.dependencies.auth import get_current_user, get_db, get_required_user
from yuxi.api.uploads import read_upload_with_limit
from yuxi.infrastructure.minio import upload_image_to_minio
from yuxi.modules.agents.services.environment import read_agent_env, verify_agent_env, write_agent_env
from yuxi.modules.identity.models import User
from yuxi.modules.identity.preferences import UserConfig, UserConfigSchema
from yuxi.modules.identity.services import api_keys as api_key_service
from yuxi.modules.identity.services.preferences import save_user_config
from yuxi.shared.datetime import format_utc_datetime

user_router = APIRouter(prefix="/user", tags=["user"])

MAX_USER_IMAGE_SIZE_BYTES = 5 * 1024 * 1024


class APIKeyCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    name: str
    user_id: int | None = None
    department_id: int | None = None
    expires_at: str | None = None
    access_level: Literal["full", "agents", "knowledge"] = "full"
    app_id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class APIKeyUpdate(BaseModel):
    name: str | None = None
    expires_at: str | None = None
    is_enabled: bool | None = None
    access_level: Literal["full", "agents", "knowledge"] | None = None
    app_id: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class APIKeyResponse(BaseModel):
    id: int
    key_prefix: str
    name: str
    access_level: Literal["full", "agents", "knowledge"]
    app_id: str | None
    user_id: int
    department_id: int | None
    expires_at: str | None
    is_enabled: bool
    last_used_at: str | None
    created_by: str
    created_at: str


class APIKeyCreateResponse(BaseModel):
    api_key: APIKeyResponse
    secret: str


class AgentEnvUpdate(BaseModel):
    env: dict[str, Any] = Field(default_factory=dict)


class AgentEnvResponse(BaseModel):
    env: dict[str, str]
    updated_at: str | None = None


async def get_logged_in_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请登录后再访问",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@user_router.get("/config", response_model=dict)
async def get_user_config(
    current_user: User = Depends(get_logged_in_user),
    db: AsyncSession = Depends(get_db),
):
    user_config = await UserConfig.load(db, current_user.uid)
    return user_config.dump_config()


@user_router.put("/config", response_model=dict)
async def update_user_config(
    data: UserConfigSchema,
    current_user: User = Depends(get_logged_in_user),
    db: AsyncSession = Depends(get_db),
):
    user_config = await save_user_config(db, uid=current_user.uid, schema=data)
    return user_config.dump_config()


@user_router.post("/upload-image", response_model=dict)
async def upload_user_image(file: UploadFile = File(...), current_user: User = Depends(get_required_user)):
    try:
        content = await read_upload_with_limit(
            file,
            max_size_bytes=MAX_USER_IMAGE_SIZE_BYTES,
            too_large_message="图片大小不能超过 5MB",
        )
        image_url = await upload_image_to_minio(
            content,
            object_prefix=f"images/{current_user.uid}",
            max_size_bytes=MAX_USER_IMAGE_SIZE_BYTES,
            too_large_message="图片大小不能超过 5MB",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"success": True, "image_url": image_url, "url": image_url}


@user_router.get("/apikey/", response_model=dict)
async def list_api_keys(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户可见的 API Key。"""
    return await api_key_service.list_api_keys(db, actor=current_user, skip=skip, limit=limit)


@user_router.post("/apikey/", response_model=APIKeyCreateResponse)
async def create_api_key(
    data: APIKeyCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await api_key_service.create_api_key(db, actor=current_user, **data.model_dump())


@user_router.get("/apikey/{api_key_id}", response_model=dict)
async def get_api_key(
    api_key_id: int,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """读取当前用户可访问的 API Key。"""
    return await api_key_service.get_api_key(db, actor=current_user, api_key_id=api_key_id)


@user_router.put("/apikey/{api_key_id}", response_model=dict)
async def update_api_key(
    api_key_id: int,
    data: APIKeyUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await api_key_service.update_api_key(db, actor=current_user, api_key_id=api_key_id, updates=data.model_dump(exclude_unset=True))


@user_router.delete("/apikey/{api_key_id}", response_model=dict)
async def delete_api_key(
    api_key_id: int,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    await api_key_service.revoke_api_key(db, actor=current_user, api_key_id=api_key_id)
    return {"success": True}


@user_router.get("/agent-env", response_model=AgentEnvResponse)
async def get_agent_env(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    result = await read_agent_env(db, uid=current_user.uid)
    return AgentEnvResponse(env=result.env, updated_at=format_utc_datetime(result.updated_at))


@user_router.put("/agent-env", response_model=AgentEnvResponse)
async def update_agent_env(
    data: AgentEnvUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    result = await write_agent_env(db, uid=current_user.uid, env=data.env)
    return AgentEnvResponse(env=result.env, updated_at=format_utc_datetime(result.updated_at))


@user_router.post("/agent-env/verify")
async def verify_saved_agent_env(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """仅验证当前认证用户已保存的配置。"""
    return await verify_agent_env(db, uid=str(current_user.uid))
