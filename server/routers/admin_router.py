import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from server.db_manager import db_manager
from server.models.token_model import AgentToken
from server.models.user_model import User, OperationLog
from server.utils.auth_middleware import get_db, get_current_user, get_admin_user, oauth2_scheme
from server.routers.auth_router import log_operation

admin = APIRouter(prefix="/admin", tags=["admin"])

# 请求和响应模型
class TokenCreate(BaseModel):
    agent_id: str
    name: str

class TokenVerify(BaseModel):
    agent_id: str
    token: str

class TokenResponse(BaseModel):
    id: int
    agent_id: str
    name: str
    token: str
    created_at: str

# 生成随机token
def generate_token(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@admin.get("/tokens", response_model=List[TokenResponse])
async def get_agent_tokens(
    agent_id: Optional[str] = Query(None),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """获取智能体的token列表（需要管理员权限）"""
    query = db.query(AgentToken)
    if agent_id:
        query = query.filter(AgentToken.agent_id == agent_id)
    tokens = query.all()
    return [token.to_dict() for token in tokens]

@admin.post("/tokens", response_model=TokenResponse)
async def create_token(
    token_data: TokenCreate,
    request: Request,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """创建新的token（需要管理员权限）"""
    # 生成随机token
    token_value = generate_token()

    # 创建token记录
    new_token = AgentToken(
        agent_id=token_data.agent_id,
        name=token_data.name,
        token=token_value
    )

    # 保存到数据库
    db.add(new_token)
    db.commit()
    db.refresh(new_token)

    # 记录操作
    log_operation(
        db,
        current_user.id,
        "创建令牌",
        f"为智能体 {token_data.agent_id} 创建访问令牌: {token_data.name}",
        request
    )

    return new_token.to_dict()

@admin.delete("/tokens/{token_id}", response_model=dict)
async def delete_token(
    token_id: int,
    request: Request,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """删除token（需要管理员权限）"""
    token = db.query(AgentToken).filter(AgentToken.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    # 记录操作信息
    log_operation(
        db,
        current_user.id,
        "删除令牌",
        f"删除令牌ID: {token_id}, 智能体: {token.agent_id}, 名称: {token.name}",
        request
    )

    db.delete(token)
    db.commit()

    return {"success": True, "message": "Token deleted"}

@admin.post("/verify_token")
async def verify_agent_token(
    token_data: TokenVerify,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """验证智能体访问令牌（所有用户都可访问）"""
    # 查找令牌
    agent_token = db.query(AgentToken).filter(
        AgentToken.agent_id == token_data.agent_id,
        AgentToken.token == token_data.token
    ).first()

    if not agent_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {"success": True, "message": "Token verified"}