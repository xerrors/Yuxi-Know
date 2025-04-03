import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from server.db_manager import db_manager
from server.models.token_model import AgentToken

admin = APIRouter(prefix="/admin", tags=["admin"])

# 依赖项：获取数据库会话
def get_db():
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()

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
    db: Session = Depends(get_db)
):
    """获取智能体的token列表"""
    query = db.query(AgentToken)
    if agent_id:
        query = query.filter(AgentToken.agent_id == agent_id)
    tokens = query.all()
    return [token.to_dict() for token in tokens]

@admin.post("/tokens", response_model=TokenResponse)
async def create_token(
    token_data: TokenCreate,
    db: Session = Depends(get_db)
):
    """创建新的token"""
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

    return new_token.to_dict()

@admin.delete("/tokens/{token_id}", response_model=dict)
async def delete_token(token_id: int, db: Session = Depends(get_db)):
    """删除token"""
    token = db.query(AgentToken).filter(AgentToken.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    db.delete(token)
    db.commit()

    return {"success": True, "message": "Token deleted"}

@admin.post("/verify_token")
async def verify_agent_token(
    token_data: TokenVerify,
    db: Session = Depends(get_db)
):
    """验证智能体访问令牌"""
    token = db.query(AgentToken).filter(
        AgentToken.agent_id == token_data.agent_id,
        AgentToken.token == token_data.token
    ).first()

    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {"success": True, "message": "Token verified"}