"""在真实 PostgreSQL 的隔离旧 Schema 上验证转换及故障负控。"""

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.support.postgres_schema import create_isolated_manager, drop_isolated_schema
from yuxi.migrations.knowledge_directories import audit, convert
from yuxi.modules.background_jobs.models import BackgroundJobRecord
from yuxi.modules.knowledge.models import KnowledgeBase, KnowledgeFile
from yuxi.shared.errors import StateConflictError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest_asyncio.fixture
async def old_schema():
    """仅放宽本例隔离表的名称约束，保留生产 ORM 的其他真实结构。"""
    schema, admin, engine, manager = await create_isolated_manager("directory_conversion")
    manager.AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        for table in [KnowledgeBase.__table__, KnowledgeFile.__table__, BackgroundJobRecord.__table__]:
            await connection.run_sync(table.create)
        await connection.execute(text("DROP INDEX uq_knowledge_files_active_name"))
        await connection.execute(text("ALTER TABLE knowledge_files DROP CONSTRAINT ck_knowledge_files_leaf_name"))
        await connection.execute(text("CREATE TABLE yuxi_schema_migrations(domain text PRIMARY KEY, version integer)"))
        await connection.execute(text("INSERT INTO yuxi_schema_migrations VALUES ('knowledge', 1)"))
        await connection.execute(text("INSERT INTO knowledge_bases(kb_id,name,kb_type) VALUES ('kb','migration','milvus')"))
    try:
        yield manager
    finally:
        await drop_isolated_schema(schema, admin, engine)


async def test_conversion_resumes_preserves_identity_and_publishes_constraint(old_schema):
    """转换中断不发布新版本；重跑保留文件身份及原件、Markdown、内容指纹。"""
    async with old_schema.get_async_session_context() as session:
        for file_id, name in [("first", "docs/Café.txt"), ("second", "docs/Cafe\u0301.txt")]:
            session.add(
                KnowledgeFile(
                    file_id=file_id,
                    kb_id="kb",
                    filename=name,
                    is_folder=False,
                    path=f"minio://knowledgebases/kb/{file_id}",
                    markdown_file=f"parsed/{file_id}",
                    content_hash="same-content",
                    created_by="u",
                )
            )
    report = await audit(old_schema)
    assert report["path_files"] == 2 and not report["blocking_ids"]
    interrupted = await convert(old_schema, stop_after=1)
    assert not interrupted["complete"]
    async with old_schema.get_async_session_context() as observer:
        assert await observer.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='knowledge'")) == 1
    assert (await convert(old_schema))["complete"]
    assert (await convert(old_schema))["complete"]
    async with old_schema.get_async_session_context() as observer:
        rows = (await observer.scalars(select(KnowledgeFile))).all()
        folders = [r for r in rows if r.is_folder]
        files = {r.file_id: r for r in rows if not r.is_folder}
        assert len(folders) == 1 and folders[0].filename == "docs"
        assert {r.filename for r in files.values()} == {"Café.txt", "Café (1).txt"}
        assert {r.parent_id for r in files.values()} == {folders[0].file_id}
        assert set(files) == {"first", "second"}
        for file_id, record in files.items():
            assert (record.path, record.markdown_file, record.content_hash) == (
                f"minio://knowledgebases/kb/{file_id}",
                f"parsed/{file_id}",
                "same-content",
            )
        assert await observer.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='knowledge'")) == 2
        with pytest.raises(IntegrityError) as error:
            await observer.execute(
                text(
                    "INSERT INTO knowledge_files(file_id,kb_id,parent_id,filename,is_folder) "
                    "VALUES ('collision','kb',:parent,'CAFÉ.txt',true)"
                ),
                {"parent": folders[0].file_id},
            )
        assert getattr(error.value.orig.__cause__, "constraint_name", None) == "uq_knowledge_files_active_name"


async def test_ambiguous_folders_prevent_any_conversion(old_schema):
    """存量重复目录必须明确处理，不能按创建时间猜测合并。"""
    async with old_schema.get_async_session_context() as session:
        for file_id, name in [("a", "Docs"), ("b", "docs")]:
            session.add(KnowledgeFile(file_id=file_id, kb_id="kb", filename=name, is_folder=True))
        session.add(KnowledgeFile(file_id="c", kb_id="kb", filename="new/file.txt", is_folder=False))
    report = await audit(old_schema)
    assert report["blocking_ids"] == ["a", "b"]
    with pytest.raises(StateConflictError):
        await convert(old_schema)
    async with old_schema.get_async_session_context() as observer:
        assert await observer.scalar(select(KnowledgeFile.filename).where(KnowledgeFile.file_id == "c")) == "new/file.txt"


async def test_unique_guard_negative_control(old_schema):
    """隔离旧库恢复缺陷：无唯一索引时 SQL 重名确实可写入。"""
    async with old_schema.get_async_session_context() as session:
        for file_id in ["a", "b"]:
            session.add(KnowledgeFile(file_id=file_id, kb_id="kb", filename="duplicate", is_folder=False))
    async with old_schema.get_async_session_context() as observer:
        assert len((await observer.scalars(select(KnowledgeFile))).all()) == 2


async def test_real_and_virtual_same_name_is_ambiguous(old_schema):
    """真实目录和历史路径同名不能被推断为同一个用户目录。"""
    async with old_schema.get_async_session_context() as session:
        session.add(KnowledgeFile(file_id="folder", kb_id="kb", filename="Docs", is_folder=True))
        session.add(KnowledgeFile(file_id="file", kb_id="kb", filename="docs/a.txt", is_folder=False))
    report = await audit(old_schema)
    assert report["blocking_ids"] == ["file", "folder"]
    with pytest.raises(StateConflictError):
        await convert(old_schema)


async def test_active_ingest_blocks_cutover(old_schema):
    """未结束的旧作业不能在新协议启用后重新生成路径型文件。"""
    async with old_schema.get_async_session_context() as session:
        session.add(BackgroundJobRecord(id="old", name="old", type="knowledge_ingest", status="pending", payload={"items": ["old"]}))
    assert (await audit(old_schema))["old_jobs"] == ["old"]
    with pytest.raises(StateConflictError):
        await convert(old_schema)


@pytest.mark.parametrize("names", [("docs", "docs/a.txt"), ("docs/a.txt", "docs/a.txt/b.txt")])
async def test_file_occupying_required_directory_blocks_before_conversion(old_schema, names):
    """历史叶子与目录前缀类型矛盾在只读审计时拒绝，不产生半程转换。"""
    async with old_schema.get_async_session_context() as session:
        for file_id, name in zip(["a", "b"], names, strict=True):
            session.add(KnowledgeFile(file_id=file_id, kb_id="kb", filename=name, is_folder=False))
    assert (await audit(old_schema))["blocking_ids"] == ["a", "b"]
    with pytest.raises(StateConflictError):
        await convert(old_schema)
    async with old_schema.get_async_session_context() as observer:
        rows = (await observer.scalars(select(KnowledgeFile).order_by(KnowledgeFile.file_id))).all()
        assert [row.filename for row in rows] == list(names)
        assert all(row.parent_id is None for row in rows)
        assert await observer.scalar(text("SELECT version FROM yuxi_schema_migrations WHERE domain='knowledge'")) == 1
