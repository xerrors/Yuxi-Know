"""停用知识库时保留持久任务，不接触外部后端。"""

from types import SimpleNamespace

import pytest

from yuxi.workers import background_jobs


@pytest.mark.asyncio
async def test_disabled_knowledge_job_keeps_pending_intent_and_can_publish_after_enable(monkeypatch):
    """队列旧消息不能消费 pending 事实，重新开启后仍可重新投递。"""
    record = SimpleNamespace(
        id="pending-knowledge-job", type="knowledge_parse", handler_version=1, status="pending", cancel_requested=False
    )
    published = []

    class Repository:
        """模拟持久任务，并拒绝关闭期间取得执行权。"""

        async def get_by_id(self, job_id):
            """读取当前持久意图。"""
            assert job_id == record.id
            return record

        async def list_pending(self, *, limit):
            """返回仍待处理的任务。"""
            return [record]

        async def claim(self, *args, **kwargs):
            """任何提前 claim 都会破坏关闭模式。"""
            record.status = "running"
            raise AssertionError("知识库关闭时不得取得任务执行权")

    async def publish(job_id):
        """记录重新投递的协议结果。"""
        published.append(job_id)

    monkeypatch.setattr(background_jobs, "BackgroundJobRepository", Repository)
    monkeypatch.setattr(background_jobs, "publish_job", publish)
    monkeypatch.setenv("YUXI_KNOWLEDGE_ENABLED", "false")

    await background_jobs.process_background_job({}, record.id)
    assert await background_jobs.publish_pending_jobs() == []
    assert record.status == "pending"
    assert published == []

    monkeypatch.setenv("YUXI_KNOWLEDGE_ENABLED", "true")
    assert await background_jobs.publish_pending_jobs() == [record.id]
    assert record.status == "pending"
    assert published == [record.id]
