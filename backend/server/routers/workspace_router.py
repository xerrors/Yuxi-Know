from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from server.utils.auth_middleware import get_required_user
from yuxi.services.workspace_service import (
    create_workspace_directory,
    delete_workspace_path,
    download_workspace_file,
    list_workspace_tree,
    read_workspace_file_content,
    upload_workspace_file,
    write_workspace_file_content,
)
from yuxi.storage.postgres.models_business import User

workspace = APIRouter(prefix="/workspace", tags=["workspace"])


class CreateWorkspaceDirectoryRequest(BaseModel):
    parent_path: str
    name: str


class UpdateWorkspaceFileContentRequest(BaseModel):
    path: str
    content: str


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


@workspace.put("/file", response_model=dict)
async def update_workspace_file(
    payload: UpdateWorkspaceFileContentRequest,
    current_user: User = Depends(get_required_user),
):
    return await write_workspace_file_content(
        path=payload.path,
        content=payload.content,
        current_user=current_user,
    )


@workspace.delete("/file", response_model=dict)
async def delete_workspace_file_route(
    path: str = Query(..., description="工作区文件或目录路径"),
    current_user: User = Depends(get_required_user),
):
    return await delete_workspace_path(path=path, current_user=current_user)


@workspace.post("/directory", response_model=dict)
async def create_workspace_directory_route(
    payload: CreateWorkspaceDirectoryRequest,
    current_user: User = Depends(get_required_user),
):
    return await create_workspace_directory(
        parent_path=payload.parent_path,
        name=payload.name,
        current_user=current_user,
    )


@workspace.post("/upload", response_model=dict)
async def upload_workspace_file_route(
    parent_path: str = Form(..., description="父目录路径"),
    file: UploadFile = File(..., description="上传文件"),
    current_user: User = Depends(get_required_user),
):
    return await upload_workspace_file(parent_path=parent_path, file=file, current_user=current_user)


@workspace.get("/download")
async def download_workspace(
    path: str = Query(..., description="工作区文件路径"),
    current_user: User = Depends(get_required_user),
):
    return await download_workspace_file(path=path, current_user=current_user)
