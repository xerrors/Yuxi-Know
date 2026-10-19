"""业务 PostgreSQL 映射。"""

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from yuxi.infrastructure.minio.client import normalize_public_minio_url
from yuxi.infrastructure.postgres.base import JSON_VALUE
from yuxi.infrastructure.postgres.base import BusinessBase as Base
from yuxi.shared.datetime import format_utc_datetime, utc_now


class AgentEnv(Base):
    """用户级 Agent 沙盒环境变量"""

    __tablename__ = "agent_envs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String, ForeignKey("users.uid"), nullable=False, unique=True, index=True)
    env = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="agent_env")


class Agent(Base):
    """用户可管理、可授权、可切换的智能体。"""

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    backend_id = Column(String(64), nullable=False, index=True)

    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(255), nullable=True)

    pics = Column(JSON, nullable=False, default=list)
    config_json = Column(JSON, nullable=False, default=dict)
    share_config = Column(JSON_VALUE, nullable=False)

    visibility = Column(String(16), nullable=False, default="private", index=True)
    is_builtin = Column(Boolean, nullable=False, default=False)

    is_default = Column(Boolean, nullable=False, default=False, index=True)

    created_by = Column(String(128), nullable=True, index=True)
    updated_by = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("visibility IN ('private', 'shared')", name="ck_agents_visibility"),
        CheckConstraint("NOT is_builtin OR visibility = 'shared'", name="ck_agents_builtin_shared"),
        CheckConstraint("visibility <> 'private' OR created_by IS NOT NULL", name="ck_agents_private_owner"),
        Index(
            "uq_agents_default",
            "is_default",
            unique=True,
            postgresql_where=is_default.is_(True),
            sqlite_where=is_default.is_(True),
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "agent_id": self.slug,
            "backend_id": self.backend_id,
            "name": self.name,
            "description": self.description,
            "icon": normalize_public_minio_url(self.icon),
            "pics": [normalize_public_minio_url(pic) for pic in (self.pics or [])],
            "config_json": self.config_json or {},
            "share_config": self.share_config or {},
            "visibility": self.visibility,
            "is_builtin": bool(self.is_builtin),
            "is_default": bool(self.is_default),
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }
