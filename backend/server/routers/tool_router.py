from fastapi import APIRouter, Depends

from yuxi.services.tool_service import get_tool_metadata
from server.utils.auth_middleware import get_admin_user
from yuxi.storage.postgres.models_business import User

tools = APIRouter(prefix="/system/tools", tags=["tools"])


@tools.get("")
async def list_tools(
    category: str = None,
    user: User = Depends(get_admin_user),
):
    """获取工具列表"""
    return {"success": True, "data": get_tool_metadata(category)}


@tools.get("/options")
async def get_tool_options(
    user: User = Depends(get_admin_user),
):
    """获取工具选项（前端下拉框用）"""
    all_tools = get_tool_metadata()
    return {"success": True, "data": [{"label": t["name"], "value": t["id"]} for t in all_tools]}
