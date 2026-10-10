"""知识库预览的注册入口、任务状态与发布控制点。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from minio.error import S3Error
from yuxi.knowledge import preview
from yuxi.services import knowledge_preview_service as service
from yuxi.services import knowledge_task_service
from yuxi.services.task_registry import get_task_definition
from yuxi.storage.minio.client import MinIOClient
from yuxi.utils.filepreview import MAX_BINARY_PREVIEW_SIZE_BYTES

from server.routers import knowledge_router


@pytest.fixture
def preview_case(monkeypatch):
    """准备元数据与外部边界，不替换被测用例。"""
    record = SimpleNamespace(
        kb_id="kb_1",
        file_id="file_1",
        filename="book.xlsx",
        original_filename=None,
        file_size=10,
        is_folder=False,
        minio_url="minio://knowledgebases/kb_1/upload/book.xlsx",
        path=None,
    )
    repo = SimpleNamespace(get_by_file_id=AsyncMock(return_value=record))
    client = SimpleNamespace(
        KB_BUCKETS={"parsed": "knowledgebases"},
        astat_file=AsyncMock(return_value=None),
        adownload_file=AsyncMock(return_value=None),
    )
    tasks = SimpleNamespace(
        find_task_by_payload=AsyncMock(return_value=None),
        enqueue_unique_by_payload=AsyncMock(return_value=(SimpleNamespace(id="preview_1", status="pending"), True)),
    )
    monkeypatch.setattr(service, "KnowledgeFileRepository", lambda: repo)
    monkeypatch.setattr(preview, "KnowledgeFileRepository", lambda: repo)
    monkeypatch.setattr(preview, "get_minio_client", lambda: client)
    monkeypatch.setattr(service, "tasker", tasks)
    return record, repo, client, tasks


@pytest.mark.parametrize("filename", ["book.xlsx", "book.xls", "report.docx", "slides.pptx"])
async def test_registration_prepares_preview_without_parsing(monkeypatch, preview_case, filename):
    """元数据注册后产生独立预览意图，原件状态仍为 uploaded。"""
    _, _, _, tasks = preview_case
    metadata = {"file_id": "file_1", "filename": filename, "size": 10, "status": "uploaded"}
    register = AsyncMock(return_value=metadata)
    monkeypatch.setattr(service.knowledge_base, "add_file_record", register)
    result = await service.register_knowledge_file("kb_1", "minio://source", params={}, operator_id="u_1")
    assert result == metadata and result["status"] == "uploaded"
    assert tasks.enqueue_unique_by_payload.await_args.kwargs["payload"] == {"kb_id": "kb_1", "file_id": "file_1"}
    assert tasks.enqueue_unique_by_payload.await_args.kwargs["payload_match"] == {"kb_id": "kb_1", "file_id": "file_1"}


@pytest.mark.parametrize(("filename", "size"), [("data.txt", 10), ("book.xlsx", MAX_BINARY_PREVIEW_SIZE_BYTES + 1)])
async def test_registration_skips_unneeded_conversion(monkeypatch, preview_case, filename, size):
    """非 Office 与超限原件不进入转换任务。"""
    _, _, _, tasks = preview_case
    monkeypatch.setattr(
        service.knowledge_base,
        "add_file_record",
        AsyncMock(return_value={"file_id": "file_1", "filename": filename, "size": size, "status": "uploaded"}),
    )
    await service.register_knowledge_file("kb_1", "minio://source", params={}, operator_id="u_1")
    tasks.enqueue_unique_by_payload.assert_not_awaited()


async def test_upload_only_route_uses_prepared_preview_registration(monkeypatch, preview_case):
    """直接添加入口必须在首次点击之前提交预览任务。"""
    _, _, _, tasks = preview_case
    item = "minio://knowledgebases/kb_1/upload/book.xlsx"
    monkeypatch.setattr(knowledge_router, "_ensure_database_supports_documents", AsyncMock())
    monkeypatch.setattr(
        service.knowledge_base,
        "add_file_record",
        AsyncMock(return_value={"file_id": "file_1", "filename": "book.xlsx", "size": 10, "status": "uploaded"}),
    )
    result = await knowledge_router.add_uploaded_documents(
        "kb_1",
        knowledge_router.AddUploadedDocumentsRequest(items=[item], params={"content_hashes": {item: "hash_1"}}),
        current_user=SimpleNamespace(uid="u_1"),
    )
    assert result["added"] == 1 and result["failed"] == 0
    tasks.enqueue_unique_by_payload.assert_awaited_once()


async def test_ingest_route_prepares_preview_before_parse(monkeypatch, preview_case):
    """批量处理入口的解析失败不取消独立预览意图。"""
    _, _, _, tasks = preview_case
    monkeypatch.setattr(
        service.knowledge_base,
        "add_file_record",
        AsyncMock(return_value={"file_id": "file_1", "filename": "book.xlsx", "size": 10, "status": "uploaded"}),
    )
    monkeypatch.setattr(service.knowledge_base, "parse_file", AsyncMock(side_effect=ValueError("解析器拒绝测试文件")))
    context = SimpleNamespace(
        payload={"kb_id": "kb_1", "items": ["minio://source"], "params": {}, "operator_id": "u_1"},
        task_id="ingest_1",
        worker_id="owner_1",
        set_progress=AsyncMock(),
        set_result=AsyncMock(),
        raise_if_cancelled=AsyncMock(),
    )
    with pytest.raises(RuntimeError, match="失败 1"):
        await knowledge_task_service.run_knowledge_ingest(context)
    tasks.enqueue_unique_by_payload.assert_awaited_once()


@pytest.mark.parametrize("entrypoint", ["upload", "ingest"])
async def test_preview_submission_failure_keeps_registered_file_and_ingest(monkeypatch, preview_case, entrypoint):
    """独立预览意图提交失败，已提交原件仍返回成功并继续解析入库。"""
    _, _, _, tasks = preview_case
    metadata = {"file_id": "file_1", "filename": "book.xlsx", "size": 10, "status": "uploaded"}
    register = AsyncMock(return_value=metadata)
    parse = AsyncMock(return_value={**metadata, "status": "parsed"})
    index = AsyncMock(return_value={**metadata, "status": "indexed"})
    monkeypatch.setattr(service.knowledge_base, "add_file_record", register)
    monkeypatch.setattr(service.knowledge_base, "parse_file", parse)
    monkeypatch.setattr(service.knowledge_base, "update_file_params", AsyncMock())
    monkeypatch.setattr(service.knowledge_base, "index_file", index)
    # 告警是同步 logger，业务结果通过返回值与实际解析参数核对。
    alert = Mock()
    monkeypatch.setattr(service, "logger", SimpleNamespace(exception=alert), raising=False)
    tasks.enqueue_unique_by_payload.side_effect = RuntimeError("测试预览意图无法提交")
    item = "minio://knowledgebases/kb_1/upload/book.xlsx"

    if entrypoint == "upload":
        monkeypatch.setattr(knowledge_router, "_ensure_database_supports_documents", AsyncMock())
        result = await knowledge_router.add_uploaded_documents(
            "kb_1",
            knowledge_router.AddUploadedDocumentsRequest(items=[item], params={"content_hashes": {item: "hash_1"}}),
            current_user=SimpleNamespace(uid="u_1"),
        )
        assert result["added"] == 1 and result["failed"] == 0
        assert result["items"][0]["file_id"] == "file_1"
        parse.assert_not_awaited()
    else:
        context = SimpleNamespace(
            payload={"kb_id": "kb_1", "items": [item], "params": {"auto_index": True}, "operator_id": "u_1"},
            task_id="ingest_1",
            worker_id="owner_1",
            set_progress=AsyncMock(),
            set_result=AsyncMock(),
            raise_if_cancelled=AsyncMock(),
        )
        result = await knowledge_task_service.run_knowledge_ingest(context)
        assert result["failed"] == 0 and result["items"] == [{**metadata, "status": "indexed"}]
        assert parse.await_args.args == ("kb_1", "file_1")
        assert index.await_args.args == ("kb_1", "file_1")

    register.assert_awaited_once()
    alert.assert_called_once()
    assert alert.call_args.args[1:] == ("kb_1", "file_1")


async def test_missing_cache_returns_loading_without_inline_conversion(monkeypatch, preview_case):
    """预览请求只提交任务并立即返回状态，转换不能在请求中执行。"""
    _, _, _, tasks = preview_case
    render = AsyncMock(side_effect=AssertionError("不能在读取请求中转换"))
    monkeypatch.setattr(preview, "convert_office_to_pdf", render)
    response = await service.read_workspace_knowledge_preview("kb_1", "file_1")
    assert response["status"] == "loading" and response["supported"]
    assert "生成预览" in response["message"]
    tasks.enqueue_unique_by_payload.assert_awaited_once()
    render.assert_not_awaited()


@pytest.mark.parametrize("status", ["pending", "running"])
async def test_repeated_read_reuses_active_preview_task(monkeypatch, preview_case, status):
    """非终态 Task 在多次读取中保持唯一意图。"""
    _, _, _, tasks = preview_case
    tasks.find_task_by_payload.return_value = SimpleNamespace(status=status)
    for _ in range(2):
        result = await service.read_workspace_knowledge_preview("kb_1", "file_1")
        assert result["status"] == "loading"
    tasks.enqueue_unique_by_payload.assert_not_awaited()


@pytest.mark.parametrize("status", ["failed", "cancelled"])
async def test_failed_preview_ends_loading(preview_case, status):
    """失败与取消必须返回错误终态，不能持续轮询。"""
    _, _, _, tasks = preview_case
    tasks.find_task_by_payload.return_value = SimpleNamespace(status=status)
    result = await service.read_workspace_knowledge_preview("kb_1", "file_1")
    assert result["status"] == "error" and not result["supported"]
    tasks.enqueue_unique_by_payload.assert_not_awaited()


async def test_cache_is_authority_after_success_or_task_failure(monkeypatch, preview_case):
    """可读取的缓存字节直接返回，不依据任务报告推断缓存缺失。"""
    _, _, client, tasks = preview_case
    client.astat_file.return_value = 16
    expected = {"content": b"%PDF-1.4", "binary": True, "preview_type": "pdf"}
    monkeypatch.setattr(service, "read_knowledge_file_preview", AsyncMock(return_value=expected))
    for _ in range(2):
        assert await service.read_workspace_knowledge_preview("kb_1", "file_1") == expected
    tasks.find_task_by_payload.assert_not_awaited()
    tasks.enqueue_unique_by_payload.assert_not_awaited()


async def test_deleted_cache_is_regenerated_after_success(preview_case):
    """成功记录不能代替已经丢失的派生对象。"""
    _, _, _, tasks = preview_case
    tasks.find_task_by_payload.return_value = SimpleNamespace(status="success")
    assert (await service.read_workspace_knowledge_preview("kb_1", "file_1"))["status"] == "loading"
    tasks.enqueue_unique_by_payload.assert_awaited_once()


@pytest.mark.parametrize("target", ["wrong_kb", "folder"])
async def test_invalid_target_never_submits_preview(preview_case, target):
    """目标文件必须属于路由已经授权的同一知识库。"""
    record, _, client, tasks = preview_case
    record.is_folder = target == "folder"
    with pytest.raises(ValueError, match="not found" if target == "wrong_kb" else "folder"):
        await service.read_workspace_knowledge_preview("other_kb" if target == "wrong_kb" else "kb_1", "file_1")
    client.astat_file.assert_not_awaited()
    tasks.enqueue_unique_by_payload.assert_not_awaited()


@pytest.mark.parametrize("reason", ["lease_lost", "source_deleted"])
async def test_worker_guard_stops_cache_write_after_ownership_or_source_loss(monkeypatch, preview_case, reason):
    """转换期间失权或原件删除时，实际缓存发布控制点拒绝写入。"""
    record, repo, _, _ = preview_case
    objects = {("knowledgebases", "kb_1/upload/book.xlsx"): b"office"}

    class Minio:
        """保留对象字节以观察发布结果。"""

        KB_BUCKETS = {"parsed": "knowledgebases"}

        async def astat_file(self, bucket, key):
            """读取对象存在性。"""
            return len(objects[(bucket, key)]) if (bucket, key) in objects else None

        async def adownload_file(self, bucket, key):
            """返回真实对象字节。"""
            return objects[(bucket, key)]

        async def aupload_file(self, bucket_name, object_name, data, content_type):
            """记录发布后的缓存。"""
            objects[(bucket_name, object_name)] = data

    monkeypatch.setattr(preview, "KnowledgeFileRepository", lambda: repo)
    monkeypatch.setattr(preview, "get_minio_client", Minio)
    monkeypatch.setattr(preview, "convert_office_to_pdf", AsyncMock(return_value=b"%PDF-1.4"))
    if reason == "source_deleted":
        repo.get_by_file_id.side_effect = [record, None]
    context = SimpleNamespace(
        payload={"kb_id": "kb_1", "file_id": "file_1"},
        set_progress=AsyncMock(),
        raise_if_cancelled=AsyncMock(
            side_effect=[None, asyncio.CancelledError("lease_lost")] if reason == "lease_lost" else [None, None]
        ),
    )
    with pytest.raises(
        asyncio.CancelledError if reason == "lease_lost" else ValueError,
        match="lease_lost" if reason == "lease_lost" else "原件已删除",
    ):
        await service.run_knowledge_preview(context)
    assert objects == {("knowledgebases", "kb_1/upload/book.xlsx"): b"office"}


def test_preview_handler_is_registered_on_shipping_path():
    """registry 必须惰性装配实际 worker Handler。"""
    assert get_task_definition("knowledge_preview").load_handler() is service.run_knowledge_preview


async def test_cache_disappearing_before_download_submits_task_without_inline_conversion(monkeypatch, preview_case):
    """缓存存在性快照失效后，实际对象缺失只能交给后台任务。"""
    _, _, client, tasks = preview_case
    client.astat_file.side_effect = [14, None]
    storage = MinIOClient()

    class MissingObject:
        """对象存储在下载时报告缓存已删除。"""

        def get_object(self, bucket_name, object_name):
            """使用真实存储错误，覆盖缓存读取和 SDK 异常边界。"""
            raise S3Error(None, "NoSuchKey", "cache disappeared", object_name, "test", "test")

    storage._client = MissingObject()
    client.adownload_file = storage.adownload_file
    converter = AsyncMock(side_effect=AssertionError("HTTP 请求不能转换 Office"))
    publisher = AsyncMock(side_effect=AssertionError("HTTP 请求不能发布缓存"))
    client.aupload_file = publisher
    monkeypatch.setattr(preview, "convert_office_to_pdf", converter)

    result = await service.read_workspace_knowledge_preview("kb_1", "file_1")

    assert result["status"] == "loading"
    tasks.enqueue_unique_by_payload.assert_awaited_once()
    converter.assert_not_awaited()
    publisher.assert_not_awaited()
