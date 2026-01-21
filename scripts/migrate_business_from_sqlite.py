"""
SQLite 到 PostgreSQL 业务数据迁移脚本

将用户、部门、对话等业务数据从 SQLite 迁移到 PostgreSQL。
迁移顺序（按外键依赖）：
1. departments (无依赖)
2. users (依赖 departments)
3. conversations (依赖 users)
4. messages (依赖 conversations)
5. tool_calls (依赖 messages)
6. conversation_stats (依赖 conversations)
7. operation_logs (依赖 users)
8. message_feedbacks (依赖 messages)
9. mcp_servers (无依赖)

用法：
    python scripts/migrate_business_from_sqlite.py --dry-run        # 预览迁移
    python scripts/migrate_business_from_sqlite.py --execute        # 执行迁移
    python scripts/migrate_business_from_sqlite.py --verify         # 验证数据
    python scripts/migrate_business_from_sqlite.py --rollback       # 回滚迁移
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, UTC
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("YUXI_SKIP_APP_INIT", "1")

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from src import config
from src.storage.db.models import (
    Base as SqliteBase,
    Department as SqliteDepartment,
    User as SqliteUser,
    Conversation as SqliteConversation,
    Message as SqliteMessage,
    ToolCall as SqliteToolCall,
    ConversationStats as SqliteConversationStats,
    OperationLog as SqliteOperationLog,
    MessageFeedback as SqliteMessageFeedback,
    MCPServer as SqliteMCPServer,
)
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


def _utc_dt(value: Any) -> datetime | None:
    """Convert various datetime formats to naive UTC datetime."""
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


class SQLiteReader:
    """SQLite 数据读取器"""

    def __init__(self):
        db_path = os.path.join(config.save_dir, "database", "server.db")
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.Session = sessionmaker(bind=self.engine)

    def get_session(self):
        return self.Session()

    def read_departments(self) -> list[SqliteDepartment]:
        with self.get_session() as session:
            return session.execute(select(SqliteDepartment)).scalars().all()

    def read_users(self) -> list[SqliteUser]:
        with self.get_session() as session:
            return session.execute(select(SqliteUser)).scalars().all()

    def read_conversations(self) -> list[SqliteConversation]:
        with self.get_session() as session:
            return session.execute(select(SqliteConversation)).scalars().all()

    def read_messages(self) -> list[SqliteMessage]:
        with self.get_session() as session:
            return session.execute(select(SqliteMessage)).scalars().all()

    def read_tool_calls(self) -> list[SqliteToolCall]:
        with self.get_session() as session:
            return session.execute(select(SqliteToolCall)).scalars().all()

    def read_conversation_stats(self) -> list[SqliteConversationStats]:
        with self.get_session() as session:
            return session.execute(select(SqliteConversationStats)).scalars().all()

    def read_operation_logs(self) -> list[SqliteOperationLog]:
        with self.get_session() as session:
            return session.execute(select(SqliteOperationLog)).scalars().all()

    def read_message_feedbacks(self) -> list[SqliteMessageFeedback]:
        with self.get_session() as session:
            return session.execute(select(SqliteMessageFeedback)).scalars().all()

    def read_mcp_servers(self) -> list[SqliteMCPServer]:
        with self.get_session() as session:
            return session.execute(select(SqliteMCPServer)).scalars().all()

    def count_table(self, table_name: str) -> int:
        with self.get_session() as session:
            result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            return result.scalar() or 0


async def migrate_departments(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, int]:
    """迁移部门数据"""
    sqlite_depts = sqlite_reader.read_departments()
    logger.info(f"准备迁移 {len(sqlite_depts)} 个部门")

    created = 0
    if dry_run:
        for sqlite_dept in sqlite_depts:
            logger.info(f"[DRY-RUN] 将创建部门: {sqlite_dept.name}")
    elif execute:
        async with pg_manager.get_async_session_context() as session:
            for sqlite_dept in sqlite_depts:
                # 检查是否已存在
                existing = await session.execute(
                    select(Department).where(Department.id == sqlite_dept.id)
                )
                if existing.scalar_one_or_none() is None:
                    dept = Department(
                        id=sqlite_dept.id,
                        name=sqlite_dept.name,
                        description=sqlite_dept.description,
                        created_at=_utc_dt(sqlite_dept.created_at),
                    )
                    session.add(dept)
                    created += 1

    return {"total": len(sqlite_depts), "created": created}


async def migrate_users(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, int]:
    """迁移用户数据"""
    sqlite_users = sqlite_reader.read_users()
    logger.info(f"准备迁移 {len(sqlite_users)} 个用户")

    created = 0
    if dry_run:
        for sqlite_user in sqlite_users:
            logger.info(f"[DRY-RUN] 将创建用户: {sqlite_user.username} ({sqlite_user.user_id})")
    elif execute:
        async with pg_manager.get_async_session_context() as session:
            for sqlite_user in sqlite_users:
                existing = await session.execute(
                    select(User).where(User.id == sqlite_user.id)
                )
                if existing.scalar_one_or_none() is None:
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
                    created += 1

    return {"total": len(sqlite_users), "created": created}


async def migrate_conversations(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, int]:
    """迁移对话数据"""
    sqlite_convs = sqlite_reader.read_conversations()
    logger.info(f"准备迁移 {len(sqlite_convs)} 个对话")

    created = 0
    if dry_run:
        for sqlite_conv in sqlite_convs:
            logger.info(f"[DRY-RUN] 将创建对话: {sqlite_conv.thread_id}")
    elif execute:
        async with pg_manager.get_async_session_context() as session:
            for sqlite_conv in sqlite_convs:
                existing = await session.execute(
                    select(Conversation).where(Conversation.id == sqlite_conv.id)
                )
                if existing.scalar_one_or_none() is None:
                    # 截断过长的 title
                    title = sqlite_conv.title
                    if title and len(title) > 255:
                        title = title[:255]
                        logger.warning(f"截断对话标题 (id={sqlite_conv.id}): 原始长度={len(sqlite_conv.title)}")
                    conv = Conversation(
                        id=sqlite_conv.id,
                        thread_id=sqlite_conv.thread_id,
                        user_id=sqlite_conv.user_id,
                        agent_id=sqlite_conv.agent_id,
                        title=title,
                        status=sqlite_conv.status,
                        created_at=_utc_dt(sqlite_conv.created_at),
                        updated_at=_utc_dt(sqlite_conv.updated_at),
                        extra_metadata=sqlite_conv.extra_metadata,
                    )
                    session.add(conv)
                    created += 1

    return {"total": len(sqlite_convs), "created": created}


async def migrate_messages(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, int]:
    """迁移消息数据"""
    sqlite_messages = sqlite_reader.read_messages()
    logger.info(f"准备迁移 {len(sqlite_messages)} 条消息")

    created = 0
    if dry_run:
        for sqlite_msg in sqlite_messages:
            logger.info(f"[DRY-RUN] 将创建消息: id={sqlite_msg.id}, conversation={sqlite_msg.conversation_id}")
    elif execute:
        async with pg_manager.get_async_session_context() as session:
            for sqlite_msg in sqlite_messages:
                existing = await session.execute(
                    select(Message).where(Message.id == sqlite_msg.id)
                )
                if existing.scalar_one_or_none() is None:
                    msg = Message(
                        id=sqlite_msg.id,
                        conversation_id=sqlite_msg.conversation_id,
                        role=sqlite_msg.role,
                        content=sqlite_msg.content,
                        message_type=sqlite_msg.message_type,
                        created_at=_utc_dt(sqlite_msg.created_at),
                        token_count=sqlite_msg.token_count,
                        extra_metadata=sqlite_msg.extra_metadata,
                        image_content=sqlite_msg.image_content,
                    )
                    session.add(msg)
                    created += 1

    return {"total": len(sqlite_messages), "created": created}


async def migrate_tool_calls(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, int]:
    """迁移工具调用数据"""
    sqlite_calls = sqlite_reader.read_tool_calls()
    logger.info(f"准备迁移 {len(sqlite_calls)} 个工具调用")

    created = 0
    if dry_run:
        for sqlite_call in sqlite_calls:
            logger.info(f"[DRY-RUN] 将创建工具调用: id={sqlite_call.id}, tool={sqlite_call.tool_name}")
    elif execute:
        async with pg_manager.get_async_session_context() as session:
            for sqlite_call in sqlite_calls:
                existing = await session.execute(
                    select(ToolCall).where(ToolCall.id == sqlite_call.id)
                )
                if existing.scalar_one_or_none() is None:
                    call = ToolCall(
                        id=sqlite_call.id,
                        message_id=sqlite_call.message_id,
                        langgraph_tool_call_id=sqlite_call.langgraph_tool_call_id,
                        tool_name=sqlite_call.tool_name,
                        tool_input=sqlite_call.tool_input,
                        tool_output=sqlite_call.tool_output,
                        status=sqlite_call.status,
                        error_message=sqlite_call.error_message,
                        created_at=_utc_dt(sqlite_call.created_at),
                    )
                    session.add(call)
                    created += 1

    return {"total": len(sqlite_calls), "created": created}


async def migrate_conversation_stats(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, int]:
    """迁移对话统计数据"""
    sqlite_stats = sqlite_reader.read_conversation_stats()
    logger.info(f"准备迁移 {len(sqlite_stats)} 条对话统计")

    created = 0
    if dry_run:
        for sqlite_stat in sqlite_stats:
            logger.info(f"[DRY-RUN] 将创建对话统计: conversation_id={sqlite_stat.conversation_id}")
    elif execute:
        async with pg_manager.get_async_session_context() as session:
            for sqlite_stat in sqlite_stats:
                existing = await session.execute(
                    select(ConversationStats).where(ConversationStats.id == sqlite_stat.id)
                )
                if existing.scalar_one_or_none() is None:
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
                    created += 1

    return {"total": len(sqlite_stats), "created": created}


async def migrate_operation_logs(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, int]:
    """迁移操作日志数据"""
    sqlite_logs = sqlite_reader.read_operation_logs()
    logger.info(f"准备迁移 {len(sqlite_logs)} 条操作日志")

    created = 0
    if dry_run:
        for sqlite_log in sqlite_logs:
            logger.info(f"[DRY-RUN] 将创建操作日志: id={sqlite_log.id}, operation={sqlite_log.operation}")
    elif execute:
        async with pg_manager.get_async_session_context() as session:
            for sqlite_log in sqlite_logs:
                existing = await session.execute(
                    select(OperationLog).where(OperationLog.id == sqlite_log.id)
                )
                if existing.scalar_one_or_none() is None:
                    log = OperationLog(
                        id=sqlite_log.id,
                        user_id=sqlite_log.user_id,
                        operation=sqlite_log.operation,
                        details=sqlite_log.details,
                        ip_address=sqlite_log.ip_address,
                        timestamp=_utc_dt(sqlite_log.timestamp),
                    )
                    session.add(log)
                    created += 1

    return {"total": len(sqlite_logs), "created": created}


async def migrate_message_feedbacks(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, int]:
    """迁移消息反馈数据"""
    sqlite_feedbacks = sqlite_reader.read_message_feedbacks()
    logger.info(f"准备迁移 {len(sqlite_feedbacks)} 条消息反馈")

    created = 0
    if dry_run:
        for sqlite_fb in sqlite_feedbacks:
            logger.info(f"[DRY-RUN] 将创建消息反馈: id={sqlite_fb.id}, rating={sqlite_fb.rating}")
    elif execute:
        async with pg_manager.get_async_session_context() as session:
            for sqlite_fb in sqlite_feedbacks:
                existing = await session.execute(
                    select(MessageFeedback).where(MessageFeedback.id == sqlite_fb.id)
                )
                if existing.scalar_one_or_none() is None:
                    fb = MessageFeedback(
                        id=sqlite_fb.id,
                        message_id=sqlite_fb.message_id,
                        user_id=sqlite_fb.user_id,
                        rating=sqlite_fb.rating,
                        reason=sqlite_fb.reason,
                        created_at=_utc_dt(sqlite_fb.created_at),
                    )
                    session.add(fb)
                    created += 1

    return {"total": len(sqlite_feedbacks), "created": created}


async def migrate_mcp_servers(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, int]:
    """迁移 MCP 服务器数据"""
    sqlite_servers = sqlite_reader.read_mcp_servers()
    logger.info(f"准备迁移 {len(sqlite_servers)} 个 MCP 服务器")

    created = 0
    if dry_run:
        for sqlite_server in sqlite_servers:
            logger.info(f"[DRY-RUN] 将创建 MCP 服务器: {sqlite_server.name}")
    elif execute:
        async with pg_manager.get_async_session_context() as session:
            for sqlite_server in sqlite_servers:
                existing = await session.execute(
                    select(MCPServer).where(MCPServer.name == sqlite_server.name)
                )
                if existing.scalar_one_or_none() is None:
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
                    created += 1

    return {"total": len(sqlite_servers), "created": created}


async def verify_migration(sqlite_reader: SQLiteReader) -> dict[str, dict]:
    """验证迁移结果"""
    # 使用 (模型, 主键列名) 格式，支持不同表使用不同的主键
    tables = [
        ("departments", Department, "id"),
        ("users", User, "id"),
        ("conversations", Conversation, "id"),
        ("messages", Message, "id"),
        ("tool_calls", ToolCall, "id"),
        ("conversation_stats", ConversationStats, "id"),
        ("operation_logs", OperationLog, "id"),
        ("message_feedbacks", MessageFeedback, "id"),
        ("mcp_servers", MCPServer, "name"),  # MCPServer 使用 name 作为主键
    ]

    results = {}
    for table_name, model, pk_column in tables:
        sqlite_count = sqlite_reader.count_table(table_name)

        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy import func
            pk_attr = getattr(model, pk_column)
            result = await session.execute(select(func.count(pk_attr)))
            pg_count = result.scalar() or 0

        results[table_name] = {
            "sqlite": sqlite_count,
            "postgresql": pg_count,
            "match": sqlite_count == pg_count,
        }

    return results


async def rollback_migration() -> None:
    """回滚迁移 - 删除所有业务数据表"""
    logger.warning("开始回滚迁移...")

    # 按外键依赖顺序删除
    tables_to_delete = [
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

    for model in tables_to_delete:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(model))
            records = result.scalars().all()
            for record in records:
                await session.delete(record)

    logger.warning("回滚完成 - 已删除所有迁移的业务数据")


async def migrate_all(sqlite_reader: SQLiteReader, dry_run: bool, execute: bool) -> dict[str, Any]:
    """执行所有迁移"""
    results = {}

    # 按外键依赖顺序迁移
    results["departments"] = await migrate_departments(sqlite_reader, dry_run, execute)
    results["users"] = await migrate_users(sqlite_reader, dry_run, execute)
    results["conversations"] = await migrate_conversations(sqlite_reader, dry_run, execute)
    results["messages"] = await migrate_messages(sqlite_reader, dry_run, execute)
    results["tool_calls"] = await migrate_tool_calls(sqlite_reader, dry_run, execute)
    results["conversation_stats"] = await migrate_conversation_stats(sqlite_reader, dry_run, execute)
    results["operation_logs"] = await migrate_operation_logs(sqlite_reader, dry_run, execute)
    results["message_feedbacks"] = await migrate_message_feedbacks(sqlite_reader, dry_run, execute)
    results["mcp_servers"] = await migrate_mcp_servers(sqlite_reader, dry_run, execute)

    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite 到 PostgreSQL 业务数据迁移")
    parser.add_argument("--dry-run", action="store_true", help="预览迁移，不执行")
    parser.add_argument("--execute", action="store_true", help="执行迁移")
    parser.add_argument("--verify", action="store_true", help="验证迁移结果")
    parser.add_argument("--rollback", action="store_true", help="回滚迁移")
    parser.add_argument("--migrate-all", action="store_true", help="迁移所有业务数据")
    parser.add_argument("--init-tables", action="store_true", help="仅初始化业务表结构")

    args = parser.parse_args()

    if not any([args.dry_run, args.execute, args.verify, args.rollback, args.migrate_all, args.init_tables]):
        args.dry_run = True

    # 初始化 PostgreSQL 管理器
    pg_manager.initialize()
    logger.info("PostgreSQL manager initialized")

    if args.init_tables:
        # 仅初始化表结构
        await pg_manager.create_business_tables()
        logger.info("业务表结构初始化完成")
        return

    if args.verify:
        # 验证模式
        sqlite_reader = SQLiteReader()
        results = await verify_migration(sqlite_reader)

        logger.info("=" * 60)
        logger.info("迁移验证结果:")
        logger.info("=" * 60)
        all_match = True
        for table_name, counts in results.items():
            status = "✓" if counts["match"] else "✗"
            logger.info(
                f"{status} {table_name}: SQLite={counts['sqlite']}, PostgreSQL={counts['postgresql']}"
            )
            if not counts["match"]:
                all_match = False
        logger.info("=" * 60)
        logger.info(f"全部匹配: {'是' if all_match else '否'}")
        return

    if args.rollback:
        # 回滚模式
        if args.dry_run:
            logger.info("[DRY-RUN] 将回滚所有迁移的业务数据")
        else:
            await rollback_migration()
        return

    # 迁移模式
    sqlite_reader = SQLiteReader()

    if args.migrate_all:
        # 检查是否需要初始化表结构
        logger.info("检查业务表结构...")
        await pg_manager.create_business_tables()
        logger.info("业务表结构就绪")

        results = await migrate_all(sqlite_reader, args.dry_run, args.execute)

        logger.info("=" * 60)
        logger.info("迁移完成:")
        for table_name, counts in results.items():
            logger.info(f"  {table_name}: {counts['created']}/{counts['total']}")
        logger.info("=" * 60)

        if not args.dry_run:
            logger.info("建议运行 --verify 验证数据完整性")
    else:
        logger.info("使用 --migrate-all 执行迁移，或使用 --verify 验证数据")


if __name__ == "__main__":
    asyncio.run(main())
