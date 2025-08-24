from fastapi import APIRouter, Depends
from src.agents.tools_factory import get_buildin_tools_info
from server.models.user_model import User
from server.utils.auth_middleware import get_required_user

tool = chat = APIRouter(prefix="/tool", tags=["tool"])

@tool.get("/tools")
async def get_tools(current_user: User = Depends(get_required_user)):
    """获取所有可用工具的信息"""
    try:
        tools_info = get_buildin_tools_info()
        return {"tools": tools_info}
    except Exception as e:
        return {"error": str(e)}
