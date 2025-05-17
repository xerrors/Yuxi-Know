from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import JSON

from server.models import Base


class Thread(Base):
    """对话线程表"""
    __tablename__ = "thread"

    id = Column(String(64), primary_key=True, index=True, comment="线程ID")
    user_id = Column(String(64), index=True, nullable=False, comment="用户ID")
    agent_id = Column(String(64), index=True, nullable=False, comment="智能体ID")
    title = Column(String(255), nullable=True, comment="标题")
    create_at = Column(DateTime, default=func.now(), comment="创建时间")
    update_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    description = Column(String(255), nullable=True, comment="描述")
    status = Column(Integer, default=1, comment="状态")