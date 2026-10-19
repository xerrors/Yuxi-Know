"""业务 PostgreSQL 映射。"""

from datetime import timedelta
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from yuxi.infrastructure.minio.client import normalize_public_minio_url
from yuxi.infrastructure.postgres.base import BusinessBase as Base
from yuxi.shared.datetime import format_utc_datetime, utc_now

MAX_LOGIN_FAILED_ATTEMPTS = 5


LOGIN_LOCK_DURATION_SECONDS = 300


IDENTITY_CHANGE_LOCK_KEY = 1498765386  # 与数据库身份触发器共用，升级不得改变已有键。


class Department(Base):
    """部门模型"""

    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True, index=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    # 关联关系
    users = relationship("User", back_populates="department", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": format_utc_datetime(self.created_at),
        }


class User(Base):
    """用户模型"""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin', 'superadmin')", name="ck_users_role"),
        UniqueConstraint("owner_user_id", "app_id", "end_user_id", name="uq_users_public_end_user_identity"),
        CheckConstraint(
            "(user_kind = 'human' AND owner_user_id IS NULL AND app_id IS NULL AND end_user_id IS NULL) "
            "OR (user_kind = 'end_user' AND owner_user_id IS NOT NULL AND app_id IS NOT NULL "
            "AND end_user_id IS NOT NULL AND role = 'user')",
            name="ck_users_public_end_user_shape",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True, index=True)  # 显示名称
    uid = Column(String, nullable=False, unique=True, index=True)  # 登录标识
    phone_number = Column(String, nullable=True, unique=True, index=True)  # 手机号
    avatar = Column(String, nullable=True)  # 头像URL
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")  # 角色: superadmin, admin, user
    user_kind = Column(String(16), nullable=False, default="human", server_default="human")
    owner_user_id = Column(Integer, ForeignKey("users.id", name="fk_users_owner_user_id"), nullable=True)
    owner_user = relationship("User", remote_side=[id], lazy="selectin", join_depth=1)
    app_id = Column(String(64), nullable=True)
    end_user_id = Column(String(128), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)  # 部门ID
    created_at = Column(DateTime(timezone=True), default=utc_now)
    last_login = Column(DateTime(timezone=True), nullable=True)

    # 登录失败限制相关字段
    login_failed_count = Column(Integer, nullable=False, default=0)  # 登录失败次数
    last_failed_login = Column(DateTime(timezone=True), nullable=True)  # 最后一次登录失败时间
    login_locked_until = Column(DateTime(timezone=True), nullable=True)  # 锁定到什么时候

    # 软删除相关字段
    is_deleted = Column(Integer, nullable=False, default=0, index=True)  # 是否已删除：0=否，1=是
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # 删除时间

    # 关联部门
    department = relationship("Department", back_populates="users")

    # 关联 API Keys
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")

    agent_env = relationship("AgentEnv", back_populates="user", cascade="all, delete-orphan", uselist=False)
    user_config = relationship("UserConfig", back_populates="user", cascade="all, delete-orphan", uselist=False)

    def to_dict(self, include_password: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "username": self.username,
            "uid": self.uid,
            "phone_number": self.phone_number,
            "avatar": normalize_public_minio_url(self.avatar),
            "role": self.role,
            "user_kind": self.user_kind,
            "department_id": self.department_id,
            "created_at": format_utc_datetime(self.created_at),
            "last_login": format_utc_datetime(self.last_login),
            "login_failed_count": self.login_failed_count,
            "last_failed_login": format_utc_datetime(self.last_failed_login),
            "login_locked_until": format_utc_datetime(self.login_locked_until),
            "is_deleted": self.is_deleted,
            "deleted_at": format_utc_datetime(self.deleted_at),
        }
        if include_password:
            result["password_hash"] = self.password_hash
        return result

    def is_login_locked(self) -> bool:
        """检查用户是否处于登录锁定状态"""
        if self.login_locked_until is None:
            return False
        return utc_now() < self.login_locked_until

    def get_remaining_lock_time(self) -> int:
        """获取剩余锁定时间（秒）"""
        if self.login_locked_until is None:
            return 0
        remaining = int((self.login_locked_until - utc_now()).total_seconds())
        return max(0, remaining)

    def increment_failed_login(self):
        """增加登录失败计数，并在达到阈值后锁定登录"""
        self.login_failed_count += 1
        self.last_failed_login = utc_now()
        if self.login_failed_count >= MAX_LOGIN_FAILED_ATTEMPTS:
            self.login_locked_until = self.last_failed_login + timedelta(seconds=LOGIN_LOCK_DURATION_SECONDS)

    def reset_failed_login(self):
        """重置登录失败相关字段"""
        self.login_failed_count = 0
        self.last_failed_login = None
        self.login_locked_until = None


class UserConfig(Base):
    """用户级配置"""

    __tablename__ = "user_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String, ForeignKey("users.uid"), nullable=False, unique=True, index=True)
    enable_memory = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="user_config")

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "enable_memory": bool(self.enable_memory),
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class APIKey(Base):
    """API Key 模型"""

    __tablename__ = "api_keys"
    __table_args__ = (CheckConstraint("access_level IN ('full', 'agents', 'knowledge')", name="ck_api_keys_access_level"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    key_prefix = Column(String(16), nullable=False)
    request_id = Column(String(64), nullable=True, unique=True, index=True)
    intent_hash = Column(String(64), nullable=True)
    name = Column(String(100), nullable=False)
    access_level = Column(String(16), nullable=False, default="full", server_default="full")
    app_id = Column(String(64), nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)

    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    created_by = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    # 关联
    user = relationship("User", back_populates="api_keys")
    department = relationship("Department")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key_prefix": self.key_prefix,
            "name": self.name,
            "access_level": self.access_level,
            "app_id": self.app_id,
            "user_id": self.user_id,
            "department_id": self.department_id,
            "expires_at": format_utc_datetime(self.expires_at),
            "is_enabled": bool(self.is_enabled),
            "last_used_at": format_utc_datetime(self.last_used_at),
            "created_by": self.created_by,
            "created_at": format_utc_datetime(self.created_at),
        }

    def is_valid(self) -> bool:
        """检查 Key 是否有效"""
        if not self.is_enabled:
            return False
        if self.revoked_at is not None:
            return False
        if self.expires_at and utc_now() > self.expires_at:
            return False
        return True


class CLIAuthSession(Base):
    """CLI 浏览器授权会话。"""

    __tablename__ = "cli_auth_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_code_hash = Column(String(64), nullable=False, unique=True, index=True)
    user_code = Column(String(16), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    key_name = Column(String(100), nullable=False)

    approved_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)

    approved_user = relationship("User")
    api_key = relationship("APIKey")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_code": self.user_code,
            "status": self.status,
            "key_name": self.key_name,
            "approved_user_id": self.approved_user_id,
            "api_key_id": self.api_key_id,
            "created_at": format_utc_datetime(self.created_at),
            "expires_at": format_utc_datetime(self.expires_at),
            "approved_at": format_utc_datetime(self.approved_at),
            "consumed_at": format_utc_datetime(self.consumed_at),
        }


class OIDCIdentity(Base):
    """issuer 和 subject 共同拥有外部身份，注销后映射仍保留。"""

    __tablename__ = "oidc_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_oidc_identity"),)
    id = Column(Integer, primary_key=True)
    issuer = Column(String(512), nullable=False)
    subject = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


class OIDCSession(Base):
    """本地 OIDC JWT 的可撤销会话，保留远端 sid 和认证签发时间。"""

    __tablename__ = "oidc_sessions"
    id = Column(String(64), primary_key=True)
    identity_id = Column(Integer, ForeignKey("oidc_identities.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_sid = Column(String(255), nullable=True, index=True)
    issued_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class OIDCLogout(Base):
    """标准登出通知的去重与短期阻断记录，和会话撤销同事务提交。"""

    __tablename__ = "oidc_logouts"
    id = Column(String(64), primary_key=True)
    issuer = Column(String(512), nullable=False, index=True)
    subject = Column(String(255), nullable=True)
    provider_sid = Column(String(255), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class RevokedAccessToken(Base):
    """有效期内的本地 JWT 撤销摘要，独立于认证中心会话。"""

    __tablename__ = "revoked_access_tokens"
    id = Column(String(64), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
