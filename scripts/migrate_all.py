"""
统一数据迁移脚本

功能：
- 阶段化执行迁移，支持单独运行某个阶段
- 详细的日志输出和进度追踪
- 支持预览、回滚和验证
- 数据完整性检查

使用方式：
    # 预览所有迁移
    python scripts/migrate_all.py --dry-run

    # 执行所有迁移
    python scripts/migrate_all.py --execute

    # 只迁移业务数据 (SQLite -> PostgreSQL)
    python scripts/migrate_all.py --execute --stage business

    # 只迁移知识库元数据 (JSON -> PostgreSQL)
    python scripts/migrate_all.py --execute --stage knowledge

    # 验证迁移结果
    python scripts/migrate_all.py --verify

    # 回滚所有迁移
    python scripts/migrate_all.py --rollback

    # 回滚指定阶段
    python scripts/migrate_all.py --rollback --stage business
"""

import argparse
import asyncio
import glob
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any
from collections.abc import Callable

# 确保路径正确
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("YUXI_SKIP_APP_INIT", "1")

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, select, text
from sqlalchemy.orm import declarative_base, sessionmaker

from src import config
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import (
    Department,
    User,
    Conversation,
    Message,
    ToolCall,
    ConversationStats,
    OperationLog,
    MessageFeedback,
    MCPServer,
)
from src.utils import logger


# ============================================================
# 迁移阶段定义
# ============================================================


@dataclass
class MigrationStage:
    """迁移阶段"""

    name: str  # 阶段名称
    description: str  # 阶段描述
    migrate_fn: Callable  # 迁移函数
    rollback_fn: Callable | None = None  # 回滚函数
    verify_fn: Callable | None = None  # 验证函数
    depends_on: list[str] = field(default_factory=list)  # 依赖阶段


@dataclass
class MigrationResult:
    """迁移结果"""

    stage_name: str
    success: bool
    dry_run: bool
    records_total: int = 0
    records_migrated: int = 0
    records_skipped: int = 0
    error: str | None = None
    duration_ms: float = 0.0


# ============================================================
# SQLite 模型定义 (仅用于迁移)
# ============================================================

SQLiteBase = declarative_base()


class SqliteDepartment(SQLiteBase):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime)


class SqliteUser(SQLiteBase):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    user_id = Column(String(50), unique=True)
    phone_number = Column(String(20))
    avatar = Column(String(500))
    password_hash = Column(String(255))
    role = Column(String(20), default="user")
    department_id = Column(Integer)
    created_at = Column(DateTime)
    last_login = Column(DateTime)
    login_failed_count = Column(Integer, default=0)
    last_failed_login = Column(DateTime)
    login_locked_until = Column(DateTime)
    is_deleted = Column(Integer, default=0)
    deleted_at = Column(DateTime)


class SqliteConversation(SQLiteBase):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    thread_id = Column(String(50), unique=True)
    user_id = Column(String(64), nullable=False)
    agent_id = Column(String(50))
    title = Column(String(255))
    status = Column(String(20), default="active")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    extra_metadata = Column(Text)


class SqliteMessage(SQLiteBase):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text)
    message_type = Column(String(20), default="text")
    created_at = Column(DateTime)
    token_count = Column(Integer)
    extra_metadata = Column(Text)
    image_content = Column(Text)


class SqliteToolCall(SQLiteBase):
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, nullable=False)
    langgraph_tool_call_id = Column(String(100))
    tool_name = Column(String(100))
    tool_input = Column(Text)
    tool_output = Column(Text)
    status = Column(String(20), default="pending")
    error_message = Column(Text)
    created_at = Column(DateTime)


class SqliteConversationStats(SQLiteBase):
    __tablename__ = "conversation_stats"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, nullable=False)
    message_count = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    model_used = Column(String(100))
    user_feedback = Column(String(20))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class SqliteOperationLog(SQLiteBase):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    operation = Column(String(100))
    details = Column(Text)
    ip_address = Column(String(50))
    timestamp = Column(DateTime)


class SqliteMessageFeedback(SQLiteBase):
    __tablename__ = "message_feedbacks"

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, nullable=False)
    user_id = Column(String(64), nullable=False)
    rating = Column(String(20))
    reason = Column(Text)
    created_at = Column(DateTime)


class SqliteMCPServer(SQLiteBase):
    __tablename__ = "mcp_servers"

    # 注意：SQLite 中 mcp_servers 表没有 id 列，主键是 name
    name = Column(String(100), unique=True, nullable=False, primary_key=True)
    description = Column(Text)
    transport = Column(String(20), default="sse")
    url = Column(String(500))
    command = Column(String(255))
    args = Column(Text)
    headers = Column(Text)
    timeout = Column(Integer)
    sse_read_timeout = Column(Integer)
    tags = Column(Text)
    icon = Column(String(500))
    enabled = Column(Integer, default=1)
    disabled_tools = Column(Text)
    created_by = Column(String(100), nullable=False)
    updated_by = Column(String(100), nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


# ============================================================
# 工具函数
# ============================================================


def _utc_dt(value: Any) -> datetime | None:
    """转换各种 datetime 格式为 naive UTC datetime"""
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC).replace(tzinfo=None)
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        try:
            dt_val = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt_val.tzinfo is None:
                return dt_val
            return dt_val.astimezone(UTC).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _load_json(path: str) -> dict[str, Any]:
    """加载 JSON 文件"""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _parse_json(value: Any) -> Any:
    """解析 JSON 字符串或返回原值"""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _log_separator(title: str = "", char: str = "=", width: int = 60) -> str:
    """生成分隔线"""
    if title:
        return f"{char * ((width - len(title) - 2) // 2)} {title} {char * ((width - len(title) - 2) // 2)}"
    return char * width


# ============================================================
# SQLite 读取器
# ============================================================


class SQLiteReader:
    """SQLite 数据读取器"""

    def __init__(self):
        db_path = os.path.join(config.save_dir, "database", "server.db")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"SQLite 数据库不存在: {db_path}")
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.Session = sessionmaker(bind=self.engine)

    def get_session(self):
        return self.Session()

    def count_table(self, table_name: str) -> int:
        with self.get_session() as session:
            result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            return result.scalar() or 0

    def read_all(self, model):
        with self.get_session() as session:
            return session.execute(select(model)).scalars().all()


# ============================================================
# 迁移阶段实现
# ============================================================


class MigrationRunner:
    """迁移运行器"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.results: list[MigrationResult] = []
        self.start_time: datetime | None = None

    def log(self, message: str, level: str = "INFO"):
        """带时间戳的日志输出"""
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        prefix = {
            "INFO": "ℹ️",
            "WARN": "⚠️",
            "ERROR": "❌",
            "SUCCESS": "✅",
            "STAGE": "🔄",
        }.get(level, "ℹ️")
        logger.info(f"[{now}] {prefix} {message}")

    async def run_stage(self, stage: MigrationStage) -> MigrationResult:
        """执行单个迁移阶段"""
        start = datetime.now()
        result = MigrationResult(stage_name=stage.name, success=False, dry_run=self.dry_run)

        self.log(_log_separator(f"阶段: {stage.name}"))
        self.log(stage.description)

        try:
            if self.dry_run:
                self.log("[DRY-RUN] 预览模式，跳过实际迁移")
                result.success = True
            else:
                result = await stage.migrate_fn(result)
                result.success = True

        except Exception as e:
            result.error = str(e)
            result.success = False
            self.log(f"迁移失败: {e}", level="ERROR")

        result.duration_ms = (datetime.now() - start).total_seconds() * 1000
        self.results.append(result)

        # 输出阶段结果
        status = "✅ 成功" if result.success else "❌ 失败"
        self.log(f"阶段完成: {status} ({result.duration_ms:.1f}ms)")
        if result.records_total > 0:
            self.log(f"  记录: {result.records_migrated}/{result.records_total} 迁移, {result.records_skipped} 跳过")

        return result

    # ----- 业务数据迁移阶段 -----

    async def migrate_business_departments(self, result: MigrationResult) -> MigrationResult:
        """迁移部门数据"""
        sqlite_reader = SQLiteReader()
        sqlite_depts = sqlite_reader.read_all(SqliteDepartment)
        result.records_total = len(sqlite_depts)

        if self.dry_run:
            for d in sqlite_depts:
                self.log(f"[DRY-RUN] 将创建部门: {d.name}")
            return result

        async with pg_manager.get_async_session_context() as session:
            for sqlite_dept in sqlite_depts:
                existing = await session.execute(select(Department).where(Department.id == sqlite_dept.id))
                if existing.scalar_one_or_none():
                    result.records_skipped += 1
                    continue
                dept = Department(
                    id=sqlite_dept.id,
                    name=sqlite_dept.name,
                    description=sqlite_dept.description,
                    created_at=_utc_dt(sqlite_dept.created_at),
                )
                session.add(dept)
                result.records_migrated += 1

        return result

    async def migrate_business_users(self, result: MigrationResult) -> MigrationResult:
        """迁移用户数据"""
        sqlite_reader = SQLiteReader()
        sqlite_users = sqlite_reader.read_all(SqliteUser)
        result.records_total = len(sqlite_users)

        if self.dry_run:
            for u in sqlite_users:
                self.log(f"[DRY-RUN] 将创建用户: {u.username} ({u.user_id})")
            return result

        async with pg_manager.get_async_session_context() as session:
            for sqlite_user in sqlite_users:
                existing = await session.execute(select(User).where(User.id == sqlite_user.id))
                if existing.scalar_one_or_none():
                    result.records_skipped += 1
                    continue
                user = User(
                    id=sqlite_user.id,
                    username=sqlite_user.username,
                    user_id=sqlite_user.user_id,
                    phone_number=sqlite_user.phone_number,
                    avatar=sqlite_user.avatar,
                    password_hash=sqlite_user.password_hash,
                    role=sqlite_user.role,
                    department_id=sqlite_user.department_id,
                    created_at=_utc_dt(sqlite_user.created_at),
                    last_login=_utc_dt(sqlite_user.last_login),
                    login_failed_count=sqlite_user.login_failed_count,
                    last_failed_login=_utc_dt(sqlite_user.last_failed_login),
                    login_locked_until=_utc_dt(sqlite_user.login_locked_until),
                    is_deleted=sqlite_user.is_deleted,
                    deleted_at=_utc_dt(sqlite_user.deleted_at),
                )
                session.add(user)
                result.records_migrated += 1

        return result

    async def migrate_business_conversations(self, result: MigrationResult) -> MigrationResult:
        """迁移对话数据"""
        sqlite_reader = SQLiteReader()
        sqlite_convs = sqlite_reader.read_all(SqliteConversation)
        result.records_total = len(sqlite_convs)

        if self.dry_run:
            for c in sqlite_convs:
                self.log(f"[DRY-RUN] 将创建对话: {c.thread_id}")
            return result

        async with pg_manager.get_async_session_context() as session:
            for sqlite_conv in sqlite_convs:
                existing = await session.execute(select(Conversation).where(Conversation.id == sqlite_conv.id))
                if existing.scalar_one_or_none():
                    result.records_skipped += 1
                    continue
                title = sqlite_conv.title
                if title and len(title) > 255:
                    title = title[:255]
                conv = Conversation(
                    id=sqlite_conv.id,
                    thread_id=sqlite_conv.thread_id,
                    user_id=sqlite_conv.user_id,
                    agent_id=sqlite_conv.agent_id,
                    title=title,
                    status=sqlite_conv.status,
                    created_at=_utc_dt(sqlite_conv.created_at),
                    updated_at=_utc_dt(sqlite_conv.updated_at),
                    extra_metadata=_parse_json(sqlite_conv.extra_metadata),
                )
                session.add(conv)
                result.records_migrated += 1

        return result

    async def migrate_business_messages(self, result: MigrationResult) -> MigrationResult:
        """迁移消息数据"""
        sqlite_reader = SQLiteReader()
        sqlite_msgs = sqlite_reader.read_all(SqliteMessage)
        result.records_total = len(sqlite_msgs)

        if self.dry_run:
            self.log(f"[DRY-RUN] 将创建 {len(sqlite_msgs)} 条消息")
            return result

        async with pg_manager.get_async_session_context() as session:
            for sqlite_msg in sqlite_msgs:
                existing = await session.execute(select(Message).where(Message.id == sqlite_msg.id))
                if existing.scalar_one_or_none():
                    result.records_skipped += 1
                    continue
                msg = Message(
                    id=sqlite_msg.id,
                    conversation_id=sqlite_msg.conversation_id,
                    role=sqlite_msg.role,
                    content=sqlite_msg.content,
                    message_type=sqlite_msg.message_type,
                    created_at=_utc_dt(sqlite_msg.created_at),
                    token_count=sqlite_msg.token_count,
                    extra_metadata=_parse_json(sqlite_msg.extra_metadata),
                    image_content=sqlite_msg.image_content,
                )
                session.add(msg)
                result.records_migrated += 1

        return result

    async def migrate_business_tool_calls(self, result: MigrationResult) -> MigrationResult:
        """迁移工具调用数据"""
        sqlite_reader = SQLiteReader()
        sqlite_calls = sqlite_reader.read_all(SqliteToolCall)
        result.records_total = len(sqlite_calls)

        if self.dry_run:
            self.log(f"[DRY-RUN] 将创建 {len(sqlite_calls)} 个工具调用")
            return result

        async with pg_manager.get_async_session_context() as session:
            for sqlite_call in sqlite_calls:
                existing = await session.execute(select(ToolCall).where(ToolCall.id == sqlite_call.id))
                if existing.scalar_one_or_none():
                    result.records_skipped += 1
                    continue
                call = ToolCall(
                    id=sqlite_call.id,
                    message_id=sqlite_call.message_id,
                    langgraph_tool_call_id=sqlite_call.langgraph_tool_call_id,
                    tool_name=sqlite_call.tool_name,
                    tool_input=_parse_json(sqlite_call.tool_input),
                    tool_output=sqlite_call.tool_output,
                    status=sqlite_call.status,
                    error_message=sqlite_call.error_message,
                    created_at=_utc_dt(sqlite_call.created_at),
                )
                session.add(call)
                result.records_migrated += 1

        return result

    async def migrate_business_stats(self, result: MigrationResult) -> MigrationResult:
        """迁移对话统计数据"""
        sqlite_reader = SQLiteReader()
        sqlite_stats = sqlite_reader.read_all(SqliteConversationStats)
        result.records_total = len(sqlite_stats)

        if self.dry_run:
            self.log(f"[DRY-RUN] 将创建 {len(sqlite_stats)} 条对话统计")
            return result

        async with pg_manager.get_async_session_context() as session:
            for sqlite_stat in sqlite_stats:
                existing = await session.execute(
                    select(ConversationStats).where(ConversationStats.id == sqlite_stat.id)
                )
                if existing.scalar_one_or_none():
                    result.records_skipped += 1
                    continue
                stat = ConversationStats(
                    id=sqlite_stat.id,
                    conversation_id=sqlite_stat.conversation_id,
                    message_count=sqlite_stat.message_count,
                    total_tokens=sqlite_stat.total_tokens,
                    model_used=sqlite_stat.model_used,
                    user_feedback=sqlite_stat.user_feedback,
                    created_at=_utc_dt(sqlite_stat.created_at),
                    updated_at=_utc_dt(sqlite_stat.updated_at),
                )
                session.add(stat)
                result.records_migrated += 1

        return result

    async def migrate_business_operation_logs(self, result: MigrationResult) -> MigrationResult:
        """迁移操作日志"""
        sqlite_reader = SQLiteReader()
        sqlite_logs = sqlite_reader.read_all(SqliteOperationLog)
        result.records_total = len(sqlite_logs)

        if self.dry_run:
            self.log(f"[DRY-RUN] 将创建 {len(sqlite_logs)} 条操作日志")
            return result

        async with pg_manager.get_async_session_context() as session:
            for sqlite_log in sqlite_logs:
                existing = await session.execute(select(OperationLog).where(OperationLog.id == sqlite_log.id))
                if existing.scalar_one_or_none():
                    result.records_skipped += 1
                    continue
                log = OperationLog(
                    id=sqlite_log.id,
                    user_id=sqlite_log.user_id,
                    operation=sqlite_log.operation,
                    details=sqlite_log.details,
                    ip_address=sqlite_log.ip_address,
                    timestamp=_utc_dt(sqlite_log.timestamp),
                )
                session.add(log)
                result.records_migrated += 1

        return result

    async def migrate_business_feedbacks(self, result: MigrationResult) -> MigrationResult:
        """迁移消息反馈"""
        sqlite_reader = SQLiteReader()
        sqlite_fbs = sqlite_reader.read_all(SqliteMessageFeedback)
        result.records_total = len(sqlite_fbs)

        if self.dry_run:
            self.log(f"[DRY-RUN] 将创建 {len(sqlite_fbs)} 条消息反馈")
            return result

        async with pg_manager.get_async_session_context() as session:
            for sqlite_fb in sqlite_fbs:
                existing = await session.execute(select(MessageFeedback).where(MessageFeedback.id == sqlite_fb.id))
                if existing.scalar_one_or_none():
                    result.records_skipped += 1
                    continue
                fb = MessageFeedback(
                    id=sqlite_fb.id,
                    message_id=sqlite_fb.message_id,
                    user_id=sqlite_fb.user_id,
                    rating=sqlite_fb.rating,
                    reason=sqlite_fb.reason,
                    created_at=_utc_dt(sqlite_fb.created_at),
                )
                session.add(fb)
                result.records_migrated += 1

        return result

    async def migrate_business_mcp_servers(self, result: MigrationResult) -> MigrationResult:
        """迁移 MCP 服务器"""
        sqlite_reader = SQLiteReader()
        sqlite_servers = sqlite_reader.read_all(SqliteMCPServer)
        result.records_total = len(sqlite_servers)

        if self.dry_run:
            for s in sqlite_servers:
                self.log(f"[DRY-RUN] 将创建 MCP 服务器: {s.name}")
            return result

        async with pg_manager.get_async_session_context() as session:
            for sqlite_server in sqlite_servers:
                existing = await session.execute(select(MCPServer).where(MCPServer.name == sqlite_server.name))
                if existing.scalar_one_or_none():
                    result.records_skipped += 1
                    continue
                server = MCPServer(
                    name=sqlite_server.name,
                    description=sqlite_server.description,
                    transport=sqlite_server.transport,
                    url=sqlite_server.url,
                    command=sqlite_server.command,
                    args=sqlite_server.args,
                    headers=sqlite_server.headers,
                    timeout=sqlite_server.timeout,
                    sse_read_timeout=sqlite_server.sse_read_timeout,
                    tags=sqlite_server.tags,
                    icon=sqlite_server.icon,
                    enabled=sqlite_server.enabled,
                    disabled_tools=sqlite_server.disabled_tools,
                    created_by=sqlite_server.created_by,
                    updated_by=sqlite_server.updated_by,
                    created_at=_utc_dt(sqlite_server.created_at),
                    updated_at=_utc_dt(sqlite_server.updated_at),
                )
                session.add(server)
                result.records_migrated += 1

        return result

    # ----- 知识库迁移阶段 -----

    async def migrate_knowledge_bases(self, result: MigrationResult) -> MigrationResult:
        """迁移知识库"""
        base_dir = os.path.join(config.save_dir, "knowledge_base_data")
        global_meta_path = os.path.join(base_dir, "global_metadata.json")
        global_meta = _load_json(global_meta_path).get("databases", {})

        kb_rows = []
        kb_type_dirs = [
            p
            for p in glob.glob(os.path.join(base_dir, "*_data"))
            if os.path.isdir(p) and os.path.basename(p) != "uploads"
        ]

        for kb_dir in kb_type_dirs:
            kb_type = os.path.basename(kb_dir)[: -len("_data")]
            meta_file = os.path.join(kb_dir, f"metadata_{kb_type}.json")
            meta = _load_json(meta_file)
            databases_meta = meta.get("databases", {})

            for db_id, db_meta in databases_meta.items():
                g = global_meta.get(db_id, {})
                created_at = _utc_dt(g.get("created_at") or db_meta.get("created_at"))
                updated_at = _utc_dt(g.get("updated_at")) or created_at
                kb_rows.append(
                    {
                        "db_id": db_id,
                        "name": g.get("name") or db_meta.get("name") or db_id,
                        "description": g.get("description") or db_meta.get("description"),
                        "kb_type": g.get("kb_type") or db_meta.get("kb_type") or kb_type,
                        "embed_info": db_meta.get("embed_info") or g.get("embed_info"),
                        "llm_info": db_meta.get("llm_info") or g.get("llm_info"),
                        "query_params": db_meta.get("query_params") or g.get("query_params"),
                        "additional_params": g.get("additional_params") or db_meta.get("metadata") or {},
                        "share_config": {"is_shared": True, "accessible_departments": []},
                        "mindmap": g.get("mindmap"),
                        "sample_questions": g.get("sample_questions") or [],
                        "created_at": created_at,
                        "updated_at": updated_at,
                    }
                )

        result.records_total = len(kb_rows)

        if self.dry_run:
            for kb in kb_rows:
                self.log(f"[DRY-RUN] 将创建知识库: {kb['name']} ({kb['db_id']})")
            return result

        from src.repositories.knowledge_base_repository import KnowledgeBaseRepository

        kb_repo = KnowledgeBaseRepository()

        for payload in kb_rows:
            db_id = payload["db_id"]
            existing = await kb_repo.get_by_id(db_id)
            if existing:
                result.records_skipped += 1
                continue
            await kb_repo.create(payload)
            result.records_migrated += 1

        return result

    async def migrate_knowledge_files(self, result: MigrationResult) -> MigrationResult:
        """迁移知识文件"""
        base_dir = os.path.join(config.save_dir, "knowledge_base_data")

        file_rows = []
        kb_type_dirs = [
            p
            for p in glob.glob(os.path.join(base_dir, "*_data"))
            if os.path.isdir(p) and os.path.basename(p) != "uploads"
        ]

        for kb_dir in kb_type_dirs:
            meta_file = os.path.join(kb_dir, f"metadata_{os.path.basename(kb_dir)[:-5]}.json")
            meta = _load_json(meta_file)
            files_meta = meta.get("files", {})

            for file_id, fmeta in files_meta.items():
                db_id = fmeta.get("database_id")
                if not db_id:
                    continue
                file_rows.append(
                    {
                        "file_id": file_id,
                        "db_id": db_id,
                        "parent_id": fmeta.get("parent_id"),
                        "filename": fmeta.get("filename") or "",
                        "original_filename": fmeta.get("original_filename") or fmeta.get("file_name"),
                        "file_type": fmeta.get("file_type") or fmeta.get("type"),
                        "path": fmeta.get("path"),
                        "minio_url": fmeta.get("minio_url"),
                        "markdown_file": fmeta.get("markdown_file"),
                        "status": fmeta.get("status"),
                        "content_hash": fmeta.get("content_hash"),
                        "file_size": fmeta.get("size") or fmeta.get("file_size"),
                        "content_type": fmeta.get("content_type"),
                        "processing_params": fmeta.get("processing_params"),
                        "is_folder": bool(fmeta.get("is_folder", False)),
                        "error_message": fmeta.get("error") or fmeta.get("error_message"),
                        "created_by": str(fmeta.get("created_by")) if fmeta.get("created_by") else None,
                        "updated_by": str(fmeta.get("updated_by")) if fmeta.get("updated_by") else None,
                        "created_at": _utc_dt(fmeta.get("created_at")),
                        "updated_at": _utc_dt(fmeta.get("updated_at")) or _utc_dt(fmeta.get("created_at")),
                    }
                )

        result.records_total = len(file_rows)

        if self.dry_run:
            folders = [f for f in file_rows if f["is_folder"]]
            files = [f for f in file_rows if not f["is_folder"]]
            self.log(f"[DRY-RUN] 将创建 {len(folders)} 个文件夹和 {len(files)} 个文件")
            return result

        from src.repositories.knowledge_file_repository import KnowledgeFileRepository

        file_repo = KnowledgeFileRepository()

        # 先插入文件夹
        folders = [(f["file_id"], f) for f in file_rows if f["is_folder"]]
        files = [(f["file_id"], f) for f in file_rows if not f["is_folder"]]

        for file_id, data in folders:
            data = data.copy()
            data.pop("file_id", None)  # 移除重复的 file_id
            await file_repo.upsert(file_id=file_id, data=data)
            result.records_migrated += 1

        for file_id, data in files:
            data = data.copy()
            data.pop("file_id", None)  # 移除重复的 file_id
            await file_repo.upsert(file_id=file_id, data=data)
            result.records_migrated += 1

        return result

    async def migrate_knowledge_evaluations(self, result: MigrationResult) -> MigrationResult:
        """迁移评估数据"""
        base_dir = os.path.join(config.save_dir, "knowledge_base_data")
        total_migrated = 0

        kb_type_dirs = [
            p
            for p in glob.glob(os.path.join(base_dir, "*_data"))
            if os.path.isdir(p) and os.path.basename(p) != "uploads"
        ]

        from src.repositories.evaluation_repository import EvaluationRepository
        from src.repositories.knowledge_base_repository import KnowledgeBaseRepository

        eval_repo = EvaluationRepository()
        kb_repo = KnowledgeBaseRepository()

        # 迁移评估基准
        benchmark_rows = []
        for kb_dir in kb_type_dirs:
            kb_type = os.path.basename(kb_dir)[: -len("_data")]
            meta_file = os.path.join(kb_dir, f"metadata_{kb_type}.json")
            meta = _load_json(meta_file)
            benchmarks_meta = meta.get("benchmarks", {})

            for db_id, bmap in benchmarks_meta.items():
                if not isinstance(bmap, dict):
                    continue
                for benchmark_id, bmeta in bmap.items():
                    benchmark_rows.append(
                        {
                            "benchmark_id": benchmark_id,
                            "db_id": db_id,
                            "name": bmeta.get("name") or benchmark_id,
                            "description": bmeta.get("description"),
                            "question_count": int(bmeta.get("question_count") or 0),
                            "has_gold_chunks": bool(bmeta.get("has_gold_chunks")),
                            "has_gold_answers": bool(bmeta.get("has_gold_answers")),
                            "data_file_path": bmeta.get("benchmark_file") or bmeta.get("data_file_path"),
                            "created_by": str(bmeta.get("created_by")) if bmeta.get("created_by") else None,
                            "created_at": _utc_dt(bmeta.get("created_at")),
                            "updated_at": _utc_dt(bmeta.get("updated_at")) or _utc_dt(bmeta.get("created_at")),
                        }
                    )

        result.records_total += len(benchmark_rows)

        if self.dry_run:
            self.log(f"[DRY-RUN] 将创建 {len(benchmark_rows)} 个评估基准")
            return result

        for payload in benchmark_rows:
            existing = await eval_repo.get_benchmark(payload["benchmark_id"])
            if existing:
                result.records_skipped += 1
                continue
            # 检查知识库是否存在
            kb = await kb_repo.get_by_id(payload["db_id"])
            if kb is None:
                self.log(f"  跳过评估基准 {payload['benchmark_id']}: 知识库 {payload['db_id']} 不存在")
                result.records_skipped += 1
                continue
            await eval_repo.create_benchmark(payload)
            total_migrated += 1

        # 迁移评估结果
        result_rows = []
        result_detail_rows = []

        for kb_dir in kb_type_dirs:
            kb_type = os.path.basename(kb_dir)[: -len("_data")]
            meta_file = os.path.join(kb_dir, f"metadata_{kb_type}.json")
            meta = _load_json(meta_file)
            databases_meta = meta.get("databases", {})

            for db_id in databases_meta.keys():
                result_dir = os.path.join(kb_dir, db_id, "results")
                if not os.path.isdir(result_dir):
                    continue
                for result_path in glob.glob(os.path.join(result_dir, "*.json")):
                    try:
                        data = _load_json(result_path)
                    except Exception:
                        continue
                    task_id = data.get("task_id") or os.path.splitext(os.path.basename(result_path))[0]
                    benchmark_id = data.get("benchmark_id")
                    started_at = _utc_dt(data.get("started_at"))
                    result_rows.append(
                        {
                            "task_id": task_id,
                            "db_id": db_id,
                            "benchmark_id": benchmark_id,
                            "status": data.get("status") or "completed",
                            "retrieval_config": data.get("retrieval_config") or {},
                            "metrics": data.get("metrics") or {},
                            "overall_score": data.get("overall_score"),
                            "total_questions": int(data.get("total_questions") or 0),
                            "completed_questions": int(data.get("completed_questions") or 0),
                            "started_at": started_at,
                            "completed_at": _utc_dt(data.get("completed_at")) or started_at,
                            "created_by": str(data.get("created_by")) if data.get("created_by") else None,
                        }
                    )
                    interim = data.get("interim_results") or data.get("results") or []
                    for idx, item in enumerate(interim):
                        result_detail_rows.append(
                            {
                                "task_id": task_id,
                                "query_index": idx,
                                "query_text": item.get("query") or item.get("query_text") or "",
                                "gold_chunk_ids": item.get("gold_chunk_ids"),
                                "gold_answer": item.get("gold_answer"),
                                "generated_answer": item.get("generated_answer"),
                                "retrieved_chunks": item.get("retrieved_chunks"),
                                "metrics": item.get("metrics") or {},
                            }
                        )

        result.records_total += len(result_rows) + len(result_detail_rows)

        if self.dry_run:
            self.log(f"[DRY-RUN] 将创建 {len(result_rows)} 个评估结果和 {len(result_detail_rows)} 条详情")
            return result

        for payload in result_rows:
            existing = await eval_repo.get_result(payload["task_id"])
            if existing:
                result.records_skipped += 1
                continue
            # 检查知识库是否存在
            kb = await kb_repo.get_by_id(payload["db_id"])
            if kb is None:
                self.log(f"  跳过评估结果 {payload['task_id']}: 知识库 {payload['db_id']} 不存在")
                result.records_skipped += 1
                continue
            await eval_repo.create_result(payload)
            total_migrated += 1

        for detail in result_detail_rows:
            await eval_repo.upsert_result_detail(
                task_id=detail["task_id"],
                query_index=detail["query_index"],
                data={
                    "query_text": detail["query_text"],
                    "gold_chunk_ids": detail["gold_chunk_ids"],
                    "gold_answer": detail["gold_answer"],
                    "generated_answer": detail["generated_answer"],
                    "retrieved_chunks": detail["retrieved_chunks"],
                    "metrics": detail["metrics"],
                },
            )
            total_migrated += 1

        result.records_migrated = total_migrated
        return result

    async def migrate_knowledge_tasks(self, result: MigrationResult) -> MigrationResult:
        """迁移任务记录"""
        tasks_json_path = os.path.join(config.save_dir, "tasks", "tasks.json")
        task_items = _load_json(tasks_json_path).get("tasks", []) or []
        result.records_total = len(task_items)

        if self.dry_run:
            self.log(f"[DRY-RUN] 将迁移 {len(task_items)} 个任务记录")
            return result

        from src.repositories.task_repository import TaskRepository

        task_repo = TaskRepository()

        for item in task_items:
            task_id = item.get("id")
            if not task_id:
                continue
            payload = item.get("payload") or {}
            await task_repo.upsert(
                task_id,
                {
                    "name": item.get("name") or "Unnamed Task",
                    "type": item.get("type") or "general",
                    "status": item.get("status") or "pending",
                    "progress": float(item.get("progress") or 0.0),
                    "message": item.get("message") or "",
                    "payload": payload,
                    "result": item.get("result"),
                    "error": item.get("error"),
                    "cancel_requested": 1 if item.get("cancel_requested") else 0,
                    "created_at": _utc_dt(item.get("created_at")),
                    "updated_at": _utc_dt(item.get("updated_at")) or _utc_dt(item.get("created_at")),
                    "started_at": _utc_dt(item.get("started_at")),
                    "completed_at": _utc_dt(item.get("completed_at")),
                },
            )
            result.records_migrated += 1

        return result

    # ----- 回滚函数 -----

    async def rollback_business(self) -> None:
        """回滚业务数据"""
        self.log(_log_separator("回滚: 业务数据"), level="WARN")

        tables = [
            MessageFeedback,
            OperationLog,
            ConversationStats,
            ToolCall,
            Message,
            Conversation,
            User,
            Department,
            MCPServer,
        ]

        for model in tables:
            async with pg_manager.get_async_session_context() as session:
                result = await session.execute(select(model))
                records = result.scalars().all()
                for record in records:
                    await session.delete(record)
                self.log(f"  已删除 {len(records)} 条 {model.__tablename__}")

    async def reset_sequences(self) -> None:
        """重置 PostgreSQL 序列值，防止主键冲突

        迁移时直接使用了 SQLite 的原始 id 值，导致 PostgreSQL 的序列未同步。
        此方法将序列值重置为当前最大 id + 1。
        """
        self.log(_log_separator("重置: PostgreSQL 序列"), level="WARN")

        tables_with_sequences = [
            ("departments", "id"),
            ("users", "id"),
            ("conversations", "id"),
            ("messages", "id"),
            ("tool_calls", "id"),
            ("conversation_stats", "id"),
            ("operation_logs", "id"),
            ("message_feedbacks", "id"),
            ("mcp_servers", None),  # name 是主键，不是 serial
            ("knowledge_bases", "id"),
            ("knowledge_files", "id"),
            ("evaluation_benchmarks", "id"),
            ("evaluation_results", "id"),
            ("evaluation_result_details", "id"),
        ]

        async with pg_manager.get_async_session_context() as session:
            for table_name, pk_column in tables_with_sequences:
                if pk_column is None:
                    continue  # 非自增主键，跳过
                try:
                    # 使用单条 SQL 获取 max_id 并重置序列
                    await session.execute(
                        text(f"""
                            SELECT setval(
                                pg_get_serial_sequence('{table_name}', '{pk_column}'),
                                COALESCE((SELECT MAX({pk_column}) FROM {table_name}), 0) + 1
                            )
                        """)
                    )
                    self.log(f"  {table_name}: 序列已重置")
                except Exception as e:
                    self.log(f"  {table_name}: 重置序列失败 - {e}", level="WARN")

    async def rollback_knowledge(self) -> None:
        """回滚知识库数据"""
        self.log(_log_separator("回滚: 知识库数据"), level="WARN")

        from src.repositories.evaluation_repository import EvaluationRepository
        from src.repositories.knowledge_base_repository import KnowledgeBaseRepository
        from src.repositories.knowledge_file_repository import KnowledgeFileRepository

        eval_repo = EvaluationRepository()
        kb_repo = KnowledgeBaseRepository()
        file_repo = KnowledgeFileRepository()

        # 回滚顺序：子表 -> 父表
        await eval_repo.delete_all()
        self.log("  已删除所有评估数据")

        rows = await kb_repo.get_all()
        for row in rows:
            await file_repo.delete_by_db_id(row.db_id)
            await kb_repo.delete(row.db_id)
        self.log(f"  已删除 {len(rows)} 个知识库及其文件")

    async def rollback_tasker(self) -> None:
        """回滚 Tasker 任务记录"""
        self.log(_log_separator("回滚: Tasker 任务记录"), level="WARN")

        from src.repositories.task_repository import TaskRepository

        task_repo = TaskRepository()
        await task_repo.delete_all()
        self.log("  已删除所有任务记录")

    # ----- 验证函数 -----

    async def verify_business(self) -> dict:
        """验证业务数据"""
        self.log(_log_separator("验证: 业务数据"))
        results = {}

        try:
            sqlite_reader = SQLiteReader()
        except FileNotFoundError:
            self.log("SQLite 数据库不存在，跳过验证", level="WARN")
            return {}

        sqlite_tables = {
            "departments": SqliteDepartment,
            "users": SqliteUser,
            "conversations": SqliteConversation,
            "messages": SqliteMessage,
            "tool_calls": SqliteToolCall,
            "conversation_stats": SqliteConversationStats,
            "operation_logs": SqliteOperationLog,
            "message_feedbacks": SqliteMessageFeedback,
            "mcp_servers": SqliteMCPServer,
        }

        pg_models = {
            "departments": Department,
            "users": User,
            "conversations": Conversation,
            "messages": Message,
            "tool_calls": ToolCall,
            "conversation_stats": ConversationStats,
            "operation_logs": OperationLog,
            "message_feedbacks": MessageFeedback,
            "mcp_servers": (MCPServer, "name"),  # MCPServer 主键是 name
        }

        for table_name, sqlite_model in sqlite_tables.items():
            sqlite_count = sqlite_reader.count_table(table_name)

            pg_model_info = pg_models[table_name]
            # 支持 (Model, pk_column) 元组形式
            if isinstance(pg_model_info, tuple):
                pg_model, pk_column = pg_model_info
            else:
                pg_model, pk_column = pg_model_info, "id"

            async with pg_manager.get_async_session_context() as session:
                from sqlalchemy import func

                result = await session.execute(select(func.count(getattr(pg_model, pk_column))))
                pg_count = result.scalar() or 0

            match = sqlite_count == pg_count
            status = "✅" if match else "❌"
            results[table_name] = {"sqlite": sqlite_count, "pg": pg_count, "match": match}
            self.log(f"  {status} {table_name}: SQLite={sqlite_count}, PG={pg_count}")

        return results

    async def verify_knowledge(self) -> dict:
        """验证知识库数据"""
        self.log(_log_separator("验证: 知识库数据"))
        results = {}

        base_dir = os.path.join(config.save_dir, "knowledge_base_data")

        # 统计 JSON 文件中的数据
        json_kb_count = 0
        json_file_count = 0

        kb_type_dirs = [
            p
            for p in glob.glob(os.path.join(base_dir, "*_data"))
            if os.path.isdir(p) and os.path.basename(p) != "uploads"
        ]

        for kb_dir in kb_type_dirs:
            kb_type = os.path.basename(kb_dir)[: -len("_data")]
            meta_file = os.path.join(kb_dir, f"metadata_{kb_type}.json")
            meta = _load_json(meta_file)
            json_kb_count += len(meta.get("databases", {}))
            json_file_count += len(meta.get("files", {}))

        from src.repositories.knowledge_base_repository import KnowledgeBaseRepository
        from src.repositories.knowledge_file_repository import KnowledgeFileRepository

        kb_repo = KnowledgeBaseRepository()
        file_repo = KnowledgeFileRepository()

        pg_kb_count = len(await kb_repo.get_all())
        # 统计文件数量
        all_files = []
        rows = await kb_repo.get_all()
        for row in rows:
            files = await file_repo.list_by_db_id(row.db_id)
            all_files.extend(files)

        pg_file_count = len(all_files)

        results["knowledge_bases"] = {"json": json_kb_count, "pg": pg_kb_count, "match": json_kb_count == pg_kb_count}
        results["knowledge_files"] = {
            "json": json_file_count,
            "pg": pg_file_count,
            "match": json_file_count == pg_file_count,
        }

        status_kb = "✅" if results["knowledge_bases"]["match"] else "❌"
        status_file = "✅" if results["knowledge_files"]["match"] else "❌"

        self.log(f"  {status_kb} knowledge_bases: JSON={json_kb_count}, PG={pg_kb_count}")
        self.log(f"  {status_file} knowledge_files: JSON={json_file_count}, PG={pg_file_count}")

        return results


# ============================================================
# 阶段定义
# ============================================================


def get_stages() -> dict[str, MigrationStage]:
    """获取所有迁移阶段"""
    runner = MigrationRunner()

    return {
        # 业务数据阶段 (按外键依赖顺序)
        "business-departments": MigrationStage(
            name="business-departments",
            description="迁移部门数据 (departments)",
            migrate_fn=runner.migrate_business_departments,
            rollback_fn=None,  # 依赖业务回滚整体处理
        ),
        "business-users": MigrationStage(
            name="business-users",
            description="迁移用户数据 (users)，依赖 departments",
            migrate_fn=runner.migrate_business_users,
            depends_on=["business-departments"],
        ),
        "business-conversations": MigrationStage(
            name="business-conversations",
            description="迁移对话数据 (conversations)",
            migrate_fn=runner.migrate_business_conversations,
            depends_on=["business-users"],
        ),
        "business-messages": MigrationStage(
            name="business-messages",
            description="迁移消息数据 (messages)，依赖 conversations",
            migrate_fn=runner.migrate_business_messages,
            depends_on=["business-conversations"],
        ),
        "business-tool-calls": MigrationStage(
            name="business-tool-calls",
            description="迁移工具调用数据 (tool_calls)，依赖 messages",
            migrate_fn=runner.migrate_business_tool_calls,
            depends_on=["business-messages"],
        ),
        "business-stats": MigrationStage(
            name="business-stats",
            description="迁移对话统计数据 (conversation_stats)",
            migrate_fn=runner.migrate_business_stats,
            depends_on=["business-conversations"],
        ),
        "business-operation-logs": MigrationStage(
            name="business-operation-logs",
            description="迁移操作日志 (operation_logs)",
            migrate_fn=runner.migrate_business_operation_logs,
            depends_on=["business-users"],
        ),
        "business-feedbacks": MigrationStage(
            name="business-feedbacks",
            description="迁移消息反馈 (message_feedbacks)",
            migrate_fn=runner.migrate_business_feedbacks,
            depends_on=["business-messages"],
        ),
        "business-mcp-servers": MigrationStage(
            name="business-mcp-servers",
            description="迁移 MCP 服务器配置 (mcp_servers)",
            migrate_fn=runner.migrate_business_mcp_servers,
        ),
        # 知识库阶段
        "knowledge-bases": MigrationStage(
            name="knowledge-bases",
            description="迁移知识库元数据 (knowledge_bases)",
            migrate_fn=runner.migrate_knowledge_bases,
        ),
        "knowledge-files": MigrationStage(
            name="knowledge-files",
            description="迁移知识文件元数据 (knowledge_files)，依赖 knowledge_bases",
            migrate_fn=runner.migrate_knowledge_files,
            depends_on=["knowledge-bases"],
        ),
        "knowledge-evaluations": MigrationStage(
            name="knowledge-evaluations",
            description="迁移评估数据 (benchmarks, results)",
            migrate_fn=runner.migrate_knowledge_evaluations,
            depends_on=["knowledge-bases"],
        ),
        # Tasker 阶段（独立于知识库）
        "tasker-tasks": MigrationStage(
            name="tasker-tasks",
            description="迁移 Tasker 任务记录 (tasks)",
            migrate_fn=runner.migrate_knowledge_tasks,
        ),
    }


def get_stage_groups() -> dict[str, list[str]]:
    """获取阶段组（批量执行）"""
    return {
        "business": [
            "business-departments",
            "business-users",
            "business-conversations",
            "business-messages",
            "business-tool-calls",
            "business-stats",
            "business-operation-logs",
            "business-feedbacks",
            "business-mcp-servers",
        ],
        "knowledge": [
            "knowledge-bases",
            "knowledge-files",
            "knowledge-evaluations",
        ],
        "tasker": [
            "tasker-tasks",
        ],
        "all": list(get_stages().keys()),
    }


# ============================================================
# 主函数
# ============================================================


async def main() -> None:
    parser = argparse.ArgumentParser(description="统一数据迁移脚本")
    parser.add_argument("--dry-run", action="store_true", help="预览迁移，不执行")
    parser.add_argument("--execute", action="store_true", help="执行迁移")
    parser.add_argument("--verify", action="store_true", help="验证迁移结果")
    parser.add_argument("--rollback", action="store_true", help="回滚迁移")
    parser.add_argument("--stage", type=str, help="指定阶段或阶段组 (如: business, knowledge, business-users)")

    args = parser.parse_args()

    # 默认dry-run
    if not any([args.dry_run, args.execute, args.verify, args.rollback]):
        args.dry_run = True

    # 初始化 PostgreSQL
    pg_manager.initialize()
    await pg_manager.create_tables()

    runner = MigrationRunner(dry_run=args.dry_run)

    # 打印标题
    if args.dry_run:
        mode = "预览模式"
    elif args.execute:
        mode = "执行模式"
    elif args.verify:
        mode = "验证模式"
    else:
        mode = "回滚模式"

    print("\n" + "=" * 60)
    print(f"🔧 数据迁移工具 | 模式: {mode}")
    print("=" * 60)

    if args.verify:
        # 验证模式
        results_business = await runner.verify_business()
        results_knowledge = await runner.verify_knowledge()

        print("\n" + "=" * 60)
        print("📊 验证结果汇总")
        print("=" * 60)

        all_match = True
        for table_name, counts in {**results_business, **results_knowledge}.items():
            if not counts.get("match", True):
                all_match = False

        print(f"全部匹配: {'✅ 是' if all_match else '❌ 否'}")
        return

    if args.rollback:
        # 回滚模式
        if args.stage == "business" or args.stage is None:
            await runner.rollback_business()
        if args.stage == "knowledge" or args.stage is None:
            await runner.rollback_knowledge()
        if args.stage == "tasker" or args.stage is None:
            await runner.rollback_tasker()

        if args.stage == "business":
            print("\n✅ 已回滚业务数据")
        elif args.stage == "knowledge":
            print("\n✅ 已回滚知识库数据")
        elif args.stage == "tasker":
            print("\n✅ 已回滚 Tasker 任务记录")
        else:
            print("\n✅ 已回滚所有迁移数据")
        return

    # 迁移模式
    stages = get_stages()
    stage_groups = get_stage_groups()

    # 确定要执行的阶段
    if args.stage and args.stage in stage_groups:
        stage_names = stage_groups[args.stage]
    elif args.stage and args.stage in stages:
        stage_names = [args.stage]
    else:
        stage_names = stage_groups["all"]

    # 按依赖顺序排序
    sorted_stages = []
    resolved = set()
    while sorted_stages.__len__() < len(stage_names):
        progress = False
        for name in stage_names:
            if name in resolved:
                continue
            stage = stages[name]
            if all(dep in resolved for dep in stage.depends_on):
                sorted_stages.append(name)
                resolved.add(name)
                progress = True
        if not progress:
            raise ValueError(f"无法解析依赖: {set(stage_names) - resolved}")

    print(f"\n📋 将执行 {len(sorted_stages)} 个阶段:")
    for name in sorted_stages:
        print(f"   - {name}")
    print()

    # 执行迁移
    total_start = datetime.now()

    for stage_name in sorted_stages:
        stage = stages[stage_name]
        await runner.run_stage(stage)

    # 重置 PostgreSQL 序列，防止后续插入时主键冲突
    if not args.dry_run:
        await runner.reset_sequences()

    total_duration = (datetime.now() - total_start).total_seconds()

    # 输出汇总
    print("\n" + "=" * 60)
    print("📊 迁移汇总")
    print("=" * 60)

    total_migrated = sum(r.records_migrated for r in runner.results)
    total_skipped = sum(r.records_skipped for r in runner.results)
    failed = [r for r in runner.results if not r.success]

    print(f"总耗时: {total_duration:.1f}s")
    print(f"迁移记录: {total_migrated}")
    print(f"跳过记录: {total_skipped}")
    print(f"失败阶段: {len(failed)}")

    if failed:
        print("\n失败详情:")
        for r in failed:
            print(f"  ❌ {r.stage_name}: {r.error}")

    if not args.dry_run:
        print("\n💡 建议运行 --verify 验证数据完整性")


if __name__ == "__main__":
    asyncio.run(main())
