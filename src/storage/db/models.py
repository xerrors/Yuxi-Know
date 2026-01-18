import datetime as dt

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from src.utils.datetime_utils import coerce_datetime, utc_isoformat, utc_now

Base = declarative_base()


def _format_utc_datetime(dt_value):
    """Helper to format datetime to UTC ISO string, assuming naive datetimes are UTC."""
    if dt_value is None:
        return None
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=dt.UTC)
    return utc_isoformat(dt_value)


## Removed legacy RDBMS knowledge models (KnowledgeDatabase/KnowledgeFile/KnowledgeNode)


class Department(Base):
    """部门模型"""

    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True, index=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    # 关联关系
    users = relationship("User", back_populates="department")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": _format_utc_datetime(self.created_at),
        }


class Conversation(Base):
    """Conversation table - new storage system"""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Primary key")
    thread_id = Column(String(64), unique=True, index=True, nullable=False, comment="Thread ID (UUID)")
    user_id = Column(String(64), index=True, nullable=False, comment="User ID")
    agent_id = Column(String(64), index=True, nullable=False, comment="Agent ID")
    title = Column(String(255), nullable=True, comment="Conversation title")
    status = Column(String(20), default="active", comment="Status: active/archived/deleted")
    created_at = Column(DateTime, default=utc_now, comment="Creation time")
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, comment="Update time")
    extra_metadata = Column(JSON, nullable=True, comment="Additional metadata")

    # Relationships
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    stats = relationship(
        "ConversationStats", back_populates="conversation", uselist=False, cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "title": self.title,
            "status": self.status,
            "created_at": _format_utc_datetime(self.created_at),
            "updated_at": _format_utc_datetime(self.updated_at),
            "metadata": self.extra_metadata or {},
        }


class Message(Base):
    """Message table - stores conversation messages"""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Primary key")
    conversation_id = Column(
        Integer, ForeignKey("conversations.id"), nullable=False, index=True, comment="Conversation ID"
    )
    role = Column(String(20), nullable=False, comment="Message role: user/assistant/system/tool")
    content = Column(Text, nullable=False, comment="Message content")
    message_type = Column(String(30), default="text", comment="Message type: text/tool_call/tool_result")
    created_at = Column(DateTime, default=utc_now, comment="Creation time")
    token_count = Column(Integer, nullable=True, comment="Token count (optional)")
    extra_metadata = Column(JSON, nullable=True, comment="Additional metadata (complete message dump)")
    image_content = Column(Text, nullable=True, comment="Base64 encoded image content for multimodal messages")

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    tool_calls = relationship("ToolCall", back_populates="message", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "message_type": self.message_type,
            "created_at": _format_utc_datetime(self.created_at),
            "token_count": self.token_count,
            "metadata": self.extra_metadata or {},
            "image_content": self.image_content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else [],
        }

    def to_simple_dict(self):
        return {
            "role": self.role,
            "content": self.content,
        }


class ToolCall(Base):
    """ToolCall table - stores tool invocations"""

    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Primary key")
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True, comment="Message ID")
    langgraph_tool_call_id = Column(
        String(100), nullable=True, index=True, comment="LangGraph tool_call_id for matching"
    )
    tool_name = Column(String(100), nullable=False, comment="Tool name")
    tool_input = Column(JSON, nullable=True, comment="Tool input parameters")
    tool_output = Column(Text, nullable=True, comment="Tool execution result")
    status = Column(String(20), default="pending", comment="Status: pending/success/error")
    error_message = Column(Text, nullable=True, comment="Error message if failed")
    created_at = Column(DateTime, default=utc_now, comment="Creation time")

    # Relationships
    message = relationship("Message", back_populates="tool_calls")

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "langgraph_tool_call_id": self.langgraph_tool_call_id,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input or {},
            "tool_output": self.tool_output,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": _format_utc_datetime(self.created_at),
        }


class ConversationStats(Base):
    """ConversationStats table - stores conversation statistics"""

    __tablename__ = "conversation_stats"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Primary key")
    conversation_id = Column(
        Integer, ForeignKey("conversations.id"), unique=True, nullable=False, comment="Conversation ID"
    )
    message_count = Column(Integer, default=0, comment="Total message count")
    total_tokens = Column(Integer, default=0, comment="Total tokens used")
    model_used = Column(String(100), nullable=True, comment="Model used")
    user_feedback = Column(JSON, nullable=True, comment="User feedback")
    created_at = Column(DateTime, default=utc_now, comment="Creation time")
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, comment="Update time")

    # Relationships
    conversation = relationship("Conversation", back_populates="stats")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
            "model_used": self.model_used,
            "user_feedback": self.user_feedback or {},
            "created_at": _format_utc_datetime(self.created_at),
            "updated_at": _format_utc_datetime(self.updated_at),
        }


class User(Base):
    """用户模型"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True, index=True)  # 显示名称，2-20字符
    user_id = Column(String, nullable=False, unique=True, index=True)  # 登录ID，根据用户名生成
    phone_number = Column(String, nullable=True, unique=True, index=True)  # 手机号，可选登录方式
    avatar = Column(String, nullable=True)  # 头像URL
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")  # 角色: superadmin, admin, user
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)  # 部门ID
    created_at = Column(DateTime, default=utc_now)
    last_login = Column(DateTime, nullable=True)

    # 登录失败限制相关字段
    login_failed_count = Column(Integer, nullable=False, default=0)  # 登录失败次数
    last_failed_login = Column(DateTime, nullable=True)  # 最后一次登录失败时间
    login_locked_until = Column(DateTime, nullable=True)  # 锁定到什么时候

    # 软删除相关字段
    is_deleted = Column(Integer, nullable=False, default=0, index=True)  # 是否已删除：0=否，1=是
    deleted_at = Column(DateTime, nullable=True)  # 删除时间

    # 关联操作日志
    operation_logs = relationship("OperationLog", back_populates="user", cascade="all, delete-orphan")

    # 关联部门
    department = relationship("Department", back_populates="users")

    def to_dict(self, include_password=False):
        # SQLite 存储 naive datetime，需要标记为 UTC 后再转换
        result = {
            "id": self.id,
            "username": self.username,
            "user_id": self.user_id,
            "phone_number": self.phone_number,
            "avatar": self.avatar,
            "role": self.role,
            "department_id": self.department_id,
            "created_at": _format_utc_datetime(self.created_at),
            "last_login": _format_utc_datetime(self.last_login),
            "login_failed_count": self.login_failed_count,
            "last_failed_login": _format_utc_datetime(self.last_failed_login),
            "login_locked_until": _format_utc_datetime(self.login_locked_until),
            "is_deleted": self.is_deleted,
            "deleted_at": _format_utc_datetime(self.deleted_at),
        }
        if include_password:
            result["password_hash"] = self.password_hash
        return result

    def is_login_locked(self):
        """检查用户是否处于登录锁定状态"""
        lock_deadline = coerce_datetime(self.login_locked_until)
        if lock_deadline is None:
            return False
        return utc_now() < lock_deadline

    def get_remaining_lock_time(self):
        """获取剩余锁定时间（秒）"""
        lock_deadline = coerce_datetime(self.login_locked_until)
        if lock_deadline is None:
            return 0
        remaining = int((lock_deadline - utc_now()).total_seconds())
        return max(0, remaining)

    def calculate_lock_duration(self):
        """根据失败次数计算锁定时长（秒）"""
        if self.login_failed_count < 10:
            return 0

        # 从第10次失败开始，等待时间从1秒开始，每次翻倍
        wait_seconds = 2 ** (self.login_failed_count - 10)

        # 最大锁定时间：365天
        max_seconds = 365 * 24 * 60 * 60
        return min(wait_seconds, max_seconds)

    def increment_failed_login(self):
        """增加登录失败次数并设置锁定时间"""
        self.login_failed_count += 1
        self.last_failed_login = utc_now()

        lock_duration = self.calculate_lock_duration()
        if lock_duration > 0:
            self.login_locked_until = utc_now() + dt.timedelta(seconds=lock_duration)

    def reset_failed_login(self):
        """重置登录失败相关字段"""
        self.login_failed_count = 0
        self.last_failed_login = None
        self.login_locked_until = None


class OperationLog(Base):
    """操作日志模型"""

    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    operation = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=utc_now)

    # 关联用户
    user = relationship("User", back_populates="operation_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "operation": self.operation,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": _format_utc_datetime(self.timestamp),
        }


class MessageFeedback(Base):
    """Message feedback table - stores user feedback on AI responses"""

    __tablename__ = "message_feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Primary key")
    message_id = Column(
        Integer, ForeignKey("messages.id"), nullable=False, index=True, comment="Message ID being rated"
    )
    user_id = Column(String(64), nullable=False, index=True, comment="User ID who provided feedback")
    rating = Column(String(10), nullable=False, comment="Feedback rating: like or dislike")
    reason = Column(Text, nullable=True, comment="Optional reason for dislike feedback")
    created_at = Column(DateTime, default=utc_now, comment="Feedback creation time")

    # Relationships
    message = relationship("Message", backref="feedbacks")

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "user_id": self.user_id,
            "rating": self.rating,
            "reason": self.reason,
            "created_at": _format_utc_datetime(self.created_at),
        }


class MCPServer(Base):
    """MCP 服务器配置模型"""

    __tablename__ = "mcp_servers"

    # 核心字段 - name 作为主键
    name = Column(String(100), primary_key=True, comment="服务器名称（唯一标识）")
    description = Column(String(500), nullable=True, comment="描述")

    # 连接配置
    transport = Column(String(20), nullable=False, comment="传输类型：sse/streamable_http/stdio")
    url = Column(String(500), nullable=True, comment="服务器 URL（sse/streamable_http）")
    command = Column(String(500), nullable=True, comment="命令（stdio）")
    args = Column(JSON, nullable=True, comment="命令参数数组（stdio）")
    headers = Column(JSON, nullable=True, comment="HTTP 请求头")
    timeout = Column(Integer, nullable=True, comment="HTTP 超时时间（秒）")
    sse_read_timeout = Column(Integer, nullable=True, comment="SSE 读取超时（秒）")

    # UI 增强字段
    tags = Column(JSON, nullable=True, comment="标签数组")
    icon = Column(String(50), nullable=True, comment="图标（emoji）")

    # 状态字段
    enabled = Column(Integer, nullable=False, default=1, comment="是否启用：1=是，0=否")
    disabled_tools = Column(JSON, nullable=True, comment="禁用的工具名称列表")

    # 用户追踪
    created_by = Column(String(100), nullable=False, comment="创建人用户名")
    updated_by = Column(String(100), nullable=False, comment="修改人用户名")

    # 时间戳
    created_at = Column(DateTime, default=utc_now, comment="创建时间")
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, comment="更新时间")

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "transport": self.transport,
            "url": self.url,
            "command": self.command,
            "args": self.args or [],
            "headers": self.headers or {},
            "timeout": self.timeout,
            "sse_read_timeout": self.sse_read_timeout,
            "tags": self.tags or [],
            "icon": self.icon,
            "enabled": bool(self.enabled),
            "disabled_tools": self.disabled_tools or [],
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": _format_utc_datetime(self.created_at),
            "updated_at": _format_utc_datetime(self.updated_at),
        }

    def to_mcp_config(self) -> dict:
        """转换为 MCP 配置格式（用于加载到 MCP_SERVERS 缓存）"""
        config = {
            "transport": self.transport,
        }
        if self.url:
            config["url"] = self.url
        if self.command:
            config["command"] = self.command
        if self.args:
            config["args"] = self.args
        if self.headers:
            config["headers"] = self.headers
        if self.timeout is not None:
            config["timeout"] = self.timeout
        if self.sse_read_timeout is not None:
            config["sse_read_timeout"] = self.sse_read_timeout
        if self.disabled_tools:
            config["disabled_tools"] = self.disabled_tools
        return config
