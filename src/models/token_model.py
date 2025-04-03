from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class AgentToken(Base):
    """智能体访问令牌模型"""
    __tablename__ = 'agent_tokens'

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False, index=True)  # 智能体ID
    name = Column(String, nullable=False)  # 令牌名称
    token = Column(String, nullable=False, unique=True)  # 令牌值
    created_at = Column(DateTime, default=func.now())  # 创建时间

    def to_dict(self):
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "name": self.name,
            "token": self.token,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }