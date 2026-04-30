from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from server.utils.auth_middleware import get_required_user
from yuxi.services.workspace_service import download_workspace_file, list_workspace_tree, read_workspace_file_content
from yuxi.storage.postgres.models_business import User

workspace = APIRouter(prefix="/workspace", tags=["workspace"])


@workspace.get("/tree", response_model=dict)
async def get_workspace_tree(
    path: str = Query("/", description="工作区目录路径"),
    current_user: User = Depends(get_required_user),
):
    return await list_workspace_tree(path=path, current_user=current_user)


@workspace.get("/file", response_model=dict)
async def get_workspace_file(
    path: str = Query(..., description="工作区文件路径"),
    current_user: User = Depends(get_required_user),
):
    return await read_workspace_file_content(path=path, current_user=current_user)


@workspace.get("/download")
async def download_workspace(
    path: str = Query(..., description="工作区文件路径"),
    current_user: User = Depends(get_required_user),
):
    return await download_workspace_file(path=path, current_user=current_user)
