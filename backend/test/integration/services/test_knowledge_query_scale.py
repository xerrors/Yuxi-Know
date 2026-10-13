"""真实 PostgreSQL 验证知识删除的固定查询量与筛选分页。"""

from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test.integration.support.postgres_schema import create_isolated_manager, drop_isolated_schema

from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.migrations.schema import create_knowledge_tables
from yuxi.modules.knowledge.cache import delete_cached_kb_config
from yuxi.infrastructure.redis import close_async_redis_client
from yuxi.modules.knowledge.evaluation.service import EvaluationService
from yuxi.modules.knowledge.models import EvaluationRun, EvaluationRunItem, KnowledgeBase, KnowledgeFile, KnowledgeProjectionOutbox
from yuxi.modules.knowledge.repositories.bases import KnowledgeBaseRepository
from yuxi.modules.knowledge.repositories.evaluation import EvaluationRepository

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest_asyncio.fixture
async def database(monkeypatch):
    """独立 schema 运行真实仓储，记录提交到数据库的语句。"""
    schema, admin, engine, manager = await create_isolated_manager("pytest_knowledge_scale")
    await create_knowledge_tables(manager)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    statements = []

    @asynccontextmanager
    async def session_context():
        """保持生产事务提交语义。"""
        async with sessions() as session, session.begin():
            yield session

    def record(conn, cursor, statement, parameters, context, executemany):
        """记录语句用于规模和锁范围断言。"""
        statements.append(statement)

    monkeypatch.setattr(pg_manager, "get_async_session_context", session_context)
    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield sessions, statements
    finally:
        await delete_cached_kb_config("scale-kb")
        await close_async_redis_client()
        await drop_isolated_schema(schema, admin, engine)


async def test_bulk_delete_fixed_query_count_and_unrelated_kb_lock(database):
    """千文件删除与小库使用固定查询量，其他库被锁仍可完成。"""
    sessions, statements = database
    async with sessions() as session, session.begin():
        session.add_all(
            [
                KnowledgeBase(kb_id="scale-kb", name="Scale", kb_type="milvus"),
                KnowledgeBase(kb_id="other-kb", name="Other", kb_type="milvus"),
            ]
        )
        await session.flush()
        session.add_all(
            KnowledgeFile(kb_id="scale-kb", file_id=f"file-{i}", filename=f"{i}.md", generation=3, status="indexed") for i in range(1200)
        )
        session.add(KnowledgeFile(kb_id="other-kb", file_id="other", filename="other.md", status="indexed"))
    async with sessions() as locked, locked.begin():
        await locked.execute(select(KnowledgeFile).where(KnowledgeFile.file_id == "other").with_for_update())
        statements.clear()
        import asyncio

        await asyncio.wait_for(KnowledgeBaseRepository().mark_deleted("scale-kb"), 5)
        delete_statements = list(statements)
    assert len(delete_statements) <= 6, delete_statements
    assert not any("FOR UPDATE" in stmt and "knowledge_files" in stmt for stmt in delete_statements)
    await KnowledgeBaseRepository().mark_deleted("scale-kb")
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(KnowledgeProjectionOutbox)) == 1201
        assert await session.scalar(select(func.count()).select_from(KnowledgeFile).where(KnowledgeFile.deleted_at.is_not(None))) == 1200
        assert await session.scalar(select(KnowledgeFile.status).where(KnowledgeFile.file_id == "other")) == "indexed"
        assert await session.scalar(select(KnowledgeBase.deleted_at).where(KnowledgeBase.kb_id == "scale-kb")) is not None
    assert not await KnowledgeBaseRepository().name_exists("sCaLe")
    assert await KnowledgeBaseRepository().name_exists("oThEr")


@pytest.mark.parametrize(
    ("result_filter", "indexes", "total"),
    [
        ("all", [2, 3], 205),
        ("answer_errors", [202, 203], 5),
        ("errors_or_low_recall", [201, 202], 6),
    ],
)
async def test_database_filters_before_offset_with_bounded_rows(database, result_filter, indexes, total):
    """跨越原批次边界的错误项按 SQL 筛选后分页，缺失指标按满分处理。"""
    sessions, statements = database
    async with sessions() as session, session.begin():
        session.add(KnowledgeBase(kb_id="scale-kb", name="Scale", kb_type="milvus"))
        await session.flush()
        session.add(EvaluationRun(run_id="run_1234abcd", kb_id="scale-kb", name="Fixed", status="completed", total_items=205))
        await session.flush()
        session.add_all(
            EvaluationRunItem(
                run_id="run_1234abcd",
                item_index=i,
                query_text=str(i),
                metrics={"score": 0.5} if i >= 200 else {"recall@10": 0.99} if i == 199 else {},
            )
            for i in range(205)
        )
    service = EvaluationService.__new__(EvaluationService)
    service.eval_repo = EvaluationRepository()
    statements.clear()
    result = await service.get_run_results("scale-kb", "run_1234abcd", page=2, page_size=2, result_filter=result_filter)
    assert [item["item_index"] for item in result["items"]] == indexes
    assert result["pagination"]["total"] == total
    row_queries = [stmt for stmt in statements if "FROM evaluation_run_items" in stmt and "count(" not in stmt]
    assert len(row_queries) == 1
    assert "LIMIT" in row_queries[0] and "OFFSET" in row_queries[0]
