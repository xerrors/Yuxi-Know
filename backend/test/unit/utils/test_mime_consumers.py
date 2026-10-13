"""文件入口共享 MIME 规则，调用方显式类型保留优先级。"""

from types import SimpleNamespace

import pytest

from yuxi.infrastructure.minio.client import MinIOClient
from yuxi.modules.knowledge.base import KnowledgeExecutor
from yuxi.shared import files


@pytest.mark.parametrize(("explicit_type", "expected"), [(None, "text/markdown"), ("text/custom", "text/custom")])
def test_minio_upload_uses_shared_fallback_and_preserves_explicit_type(monkeypatch, explicit_type, expected):
    """上传协议输出保留源字节，显式类型优先于共享 fallback。"""
    monkeypatch.setattr(files.mimetypes, "guess_type", lambda _path: (None, None))
    objects = {}

    class ObjectStore:
        """保存上传协议结果，作为对象内容与类型的 oracle。"""

        def put_object(self, *, bucket_name, object_name, data, length, content_type):
            """读取真实输入流并保存协议媒体类型。"""
            content = data.read()
            assert len(content) == length
            objects[(bucket_name, object_name)] = (content, content_type)
            return object()

    client = MinIOClient()
    client._client = ObjectStore()
    monkeypatch.setattr(client, "ensure_bucket_exists", lambda **_kwargs: True)
    client.upload_file("knowledgebases", "report.MD", b"# hello", content_type=explicit_type)
    assert objects == {("knowledgebases", "report.MD"): (b"# hello", expected)}


@pytest.mark.asyncio
@pytest.mark.parametrize(("metadata_type", "expected"), [(None, "text/markdown"), ("text/custom", "text/custom")])
async def test_knowledge_download_uses_shared_fallback_and_preserves_metadata_type(monkeypatch, metadata_type, expected):
    """下载保留元数据类型优先，缺失时使用共享后缀规则。"""
    monkeypatch.setattr(files.mimetypes, "guess_type", lambda _path: (None, None))
    source = "minio://knowledgebases/report.MD"

    async def get_metadata(kb_id, file_id):
        """提供通过知识库授权边界后的元数据。"""
        assert (kb_id, file_id) == ("kb-1", "file-1")
        return {"filename": "report.MD", "content_type": metadata_type}

    async def read_bytes(path):
        """返回源对象字节。"""
        assert path == source
        return b"# hello"

    owner = SimpleNamespace(_get_file_meta=get_metadata, _original_file_path=lambda _meta: source, _read_minio_bytes=read_bytes)
    result = await KnowledgeExecutor.get_file_download(owner, "kb-1", "file-1")
    assert result == {"filename": "report.MD", "content": b"# hello", "media_type": expected}
