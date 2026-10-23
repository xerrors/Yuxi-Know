"""共享调用方事务的目录读写及名称分配。"""

from os.path import splitext
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.knowledge.file_status import FileStatus
from yuxi.modules.knowledge.models import KnowledgeBase, KnowledgeFile, KnowledgeImport
from yuxi.modules.knowledge.names import suffixed_name
from yuxi.shared.errors import InvalidInputError, InvalidOperationError, ResourceNotFoundError, StateConflictError


class DirectoryRepository:
    """目录锁、父关系及名称查询只使用传入的事务。"""

    async def lock(self, session: AsyncSession, kb_id: str) -> KnowledgeBase:
        """统一锁序为目录树、知识库、节点，防止删除与导入交错。"""
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(kb_id))))
        kb = await session.scalar(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id).with_for_update())
        if kb is None or kb.deleted_at is not None:
            raise ResourceNotFoundError("知识库不存在")
        return kb

    async def lock_import(self, session: AsyncSession, operator_id: str, identity: str) -> None:
        """跨知识库串行化同一操作者的导入身份。"""
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"knowledge-import:{operator_id}:{identity}"))))

    async def manifest_keys(self, session: AsyncSession, paths: list[str]) -> list[str]:
        """在写入前批量生成与名称索引同规则的清单键。"""
        return list(
            (
                await session.scalars(
                    text("SELECT normalize(lower(normalize(path, NFC)), NFC) FROM unnest(CAST(:paths AS text[])) AS path"), {"paths": paths}
                )
            ).all()
        )

    async def node(self, session: AsyncSession, kb_id: str, file_id: str) -> KnowledgeFile:
        """只读取目标知识库有效节点。"""
        node = await session.scalar(
            select(KnowledgeFile)
            .where(KnowledgeFile.kb_id == kb_id, KnowledgeFile.file_id == file_id, KnowledgeFile.deleted_at.is_(None))
            .with_for_update()
        )
        if node is None:
            raise ResourceNotFoundError("文件或目录不存在")
        return node

    async def parent(self, session: AsyncSession, kb_id: str, parent_id: str | None) -> None:
        """父节点必须是同库有效目录。"""
        if parent_id is not None:
            node = await self.node(session, kb_id, parent_id)
            if not node.is_folder:
                raise InvalidOperationError("目标不是文件夹")

    async def named(
        self, session: AsyncSession, kb_id: str, parent_id: str | None, name: str, exclude_id: str | None = None
    ) -> KnowledgeFile | None:
        """名称比较与唯一索引使用同一 PostgreSQL 表达式。"""
        return await session.scalar(
            select(KnowledgeFile).where(
                KnowledgeFile.file_id != exclude_id if exclude_id else True,
                KnowledgeFile.kb_id == kb_id,
                KnowledgeFile.parent_id.is_not_distinct_from(parent_id),
                KnowledgeFile.deleted_at.is_(None),
                func.normalize(func.lower(func.normalize(func.btrim(KnowledgeFile.filename), text("NFC"))), text("NFC"))
                == func.normalize(func.lower(func.normalize(func.btrim(name), text("NFC"))), text("NFC")),
            )
        )

    async def folder(
        self, session: AsyncSession, kb_id: str, parent_id: str | None, name: str, operator_id: str | None, *, reuse: bool
    ) -> KnowledgeFile:
        """创建目录；只有上传路径允许复用已有目录。"""
        existing = await self.named(session, kb_id, parent_id, name)
        if existing is not None:
            if reuse and existing.is_folder:
                return existing
            raise StateConflictError(f"名称「{name}」已被占用", code="name_conflict")
        node = KnowledgeFile(
            file_id=f"folder-{uuid4()}",
            kb_id=kb_id,
            parent_id=parent_id,
            filename=name,
            path=name,
            file_type="folder",
            is_folder=True,
            status=FileStatus.FOLDER_READY,
            created_by=operator_id,
        )
        session.add(node)
        await self.flush(session)
        return node

    async def available_name(
        self, session: AsyncSession, kb_id: str, parent_id: str | None, requested: str, exclude_id: str | None = None
    ) -> str:
        """在持有目录树锁的事务内选择最小可用叶子名。"""
        if await self.named(session, kb_id, parent_id, requested, exclude_id=exclude_id) is None:
            return requested
        suffixed_name(requested, 1)  # 先验证扩展名保留后仍有主名预算。
        stem, extension = splitext(requested)
        # 在数据库内寻找最小空位，避免高重名批次产生平方级网络往返。
        statement = text("""
            WITH siblings AS MATERIALIZED (
                SELECT normalize(lower(normalize(btrim(filename), NFC)), NFC) AS key
                FROM knowledge_files
                WHERE kb_id = :kb_id AND parent_id IS NOT DISTINCT FROM CAST(:parent_id AS text)
                  AND deleted_at IS NULL AND (CAST(:exclude_id AS text) IS NULL OR file_id <> :exclude_id)
            ), candidates AS (
                SELECT n, left(:stem, 512 - length(:extension) - length(' (' || n || ')'))
                       || ' (' || n || ')' || :extension AS name
                FROM generate_series(1, (SELECT count(*)::integer + 1 FROM siblings)) AS n
                WHERE 512 - length(:extension) - length(' (' || n || ')') >= 1
            )
            SELECT name FROM candidates
            WHERE NOT EXISTS (
                SELECT 1 FROM siblings WHERE key = normalize(lower(normalize(name, NFC)), NFC)
            )
            ORDER BY n LIMIT 1
        """)
        candidate = (
            await session.execute(
                statement,
                {
                    "kb_id": kb_id,
                    "parent_id": parent_id,
                    "exclude_id": exclude_id,
                    "stem": stem,
                    "extension": extension,
                },
            )
        ).scalar_one_or_none()
        if candidate is None:
            raise InvalidInputError("扩展名过长，无法分配冲突后缀")
        return candidate

    async def subtree(self, session: AsyncSession, kb_id: str, file_id: str) -> list[KnowledgeFile]:
        """在持有树锁时锁定整个有效子树，删除期间不接受新后代。"""
        tree = (
            select(KnowledgeFile.file_id)
            .where(
                KnowledgeFile.kb_id == kb_id,
                KnowledgeFile.file_id == file_id,
                KnowledgeFile.deleted_at.is_(None),
            )
            .cte("directory_subtree", recursive=True)
        )
        tree = tree.union_all(
            select(KnowledgeFile.file_id).where(
                KnowledgeFile.kb_id == kb_id,
                KnowledgeFile.parent_id == tree.c.file_id,
                KnowledgeFile.deleted_at.is_(None),
            )
        )
        return list(
            (
                await session.scalars(
                    select(KnowledgeFile)
                    .where(
                        KnowledgeFile.file_id.in_(select(tree.c.file_id)),
                    )
                    .order_by(KnowledgeFile.file_id)
                    .with_for_update()
                )
            ).all()
        )

    async def receipt(self, session: AsyncSession, operator_id: str, import_id: str) -> KnowledgeImport | None:
        """已删除节点的回执仍参与重试判定。"""
        return await session.scalar(
            select(KnowledgeImport).where(
                KnowledgeImport.operator_id == operator_id,
                KnowledgeImport.import_id == import_id,
            )
        )

    async def flush(self, session: AsyncSession) -> None:
        """只将指定名称索引冲突翻译为领域错误。"""
        try:
            await session.flush()
        except IntegrityError as exc:
            if getattr(exc.orig.__cause__, "constraint_name", None) != "uq_knowledge_files_active_name":
                raise
            raise StateConflictError("同级名称已被占用", code="name_conflict") from exc
