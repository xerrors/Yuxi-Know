"""全库状态、错误详情及既有统计的只读展示。"""

from uuid import uuid4

import pytest
from sqlalchemy import select, update

from test.integration.api.test_knowledge_directory_imports import directory_kb as directory_kb
from yuxi.modules.background_jobs.models import BackgroundJobRecord
from yuxi.modules.identity.models import User
from yuxi.modules.knowledge.models import KnowledgeBase, KnowledgeFile

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_summary_includes_hidden_failures_and_preserves_error(test_client, admin_headers, directory_kb, postgres_sessions):
    """错误在子目录且不在当前页，摘要仍显示；目录和删除记录不参与计数。"""
    kb_id, folder = directory_kb, "summary-folder-" + uuid4().hex
    error = "<parser>\n" + "无法读取段落。" * 100
    async with postgres_sessions() as session:
        session.add(KnowledgeFile(kb_id=kb_id, file_id=folder, filename="资料", is_folder=True, status="done", token_count=999))
        await session.flush()
        for name, state, parent, deleted in [
            ("a", "error_parsing", folder, False),
            ("b", "parsed", None, False),
            ("c", "failed", None, False),
            ("d", "error_parsing", None, True),
        ]:
            from yuxi.shared.datetime import utc_now

            session.add(
                KnowledgeFile(
                    kb_id=kb_id,
                    file_id=uuid4().hex,
                    filename=name,
                    status=state,
                    parent_id=parent,
                    is_folder=False,
                    error_message=error if name == "a" else None,
                    deleted_at=utc_now() if deleted else None,
                )
            )
        await session.commit()
    root = f"/api/knowledge/knowledge-bases/{kb_id}"
    response = await test_client.get(root + "/documents", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["stats"]["file_status_counts"] == {"error_parsing": 1, "parsed": 1, "failed": 1}
    assert data["stats"]["file_count"] == 3 and data["stats"]["token_count"] == 0
    assert all(row["status"] != "error_parsing" for row in data["items"])
    nested = await test_client.get(root + "/documents", params={"parent_id": folder}, headers=admin_headers)
    assert nested.json()["items"][0]["error_message"] == error
    detail = await test_client.get(root, headers=admin_headers)
    assert detail.json()["stats"]["file_status_counts"] == data["stats"]["file_status_counts"]


async def test_summary_readonly_preserves_persisted_statistics(test_client, standard_user, directory_kb, postgres_sessions):
    """只读管理员可读错误与既有计数，刷新不重新计算或产生后台作业。"""
    async with postgres_sessions() as session:
        await session.execute(update(User).where(User.uid == standard_user["user"]["uid"]).values(role="admin"))
        await session.execute(
            update(KnowledgeBase)
            .where(KnowledgeBase.kb_id == directory_kb)
            .values(
                share_config={
                    "version": 2,
                    "read_scope": {"access_level": "global", "department_ids": [], "user_uids": []},
                    "manage_scope": None,
                }
            )
        )
        session.add(
            KnowledgeFile(
                kb_id=directory_kb,
                file_id=uuid4().hex,
                filename="readonly-error",
                is_folder=False,
                status="error_parsing",
                error_message="读取者也能查看的失败原因",
                token_count=91,
                chunk_count=7,
            )
        )
        await session.commit()
    root = f"/api/knowledge/knowledge-bases/{directory_kb}"
    read = await test_client.get(root + "/documents", headers=standard_user["headers"])
    assert read.status_code == 200, read.text
    assert read.json()["items"][0]["error_message"] == "读取者也能查看的失败原因"
    assert read.json()["stats"]["token_count"] == 91
    assert read.json()["stats"]["chunk_count"] == 7
    for _ in range(2):
        detail = await test_client.get(root, headers=standard_user["headers"])
        assert detail.status_code == 200, detail.text
        assert detail.json()["stats"]["token_count"] == 91
        assert detail.json()["stats"]["chunk_count"] == 7
    async with postgres_sessions() as observer:
        file = await observer.scalar(select(KnowledgeFile).where(KnowledgeFile.kb_id == directory_kb))
        assert (file.token_count, file.chunk_count, file.error_message) == (91, 7, "读取者也能查看的失败原因")
        assert not (
            await observer.scalars(select(BackgroundJobRecord).where(BackgroundJobRecord.payload["kb_id"].as_string() == directory_kb))
        ).all()
