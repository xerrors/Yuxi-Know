"""对象读取预算与响应资源清理。"""

from io import BytesIO
from types import SimpleNamespace

import pytest

from yuxi.infrastructure.minio import MinIOClient, ObjectSizeLimitError


@pytest.mark.asyncio
@pytest.mark.parametrize("async_read", [False, True])
@pytest.mark.parametrize("content,limit", [(b"", 0), (b"12345678", 8), (b"123", 8), (b"x" * 32, 8)])
async def test_bounded_object_download_reads_at_most_limit_plus_one_and_closes(async_read, content, limit):
    response = _Response(content)
    storage = MinIOClient()
    storage._client = SimpleNamespace(get_object=lambda **_kwargs: response)

    if len(content) > limit:
        with pytest.raises(ObjectSizeLimitError):
            if async_read:
                await storage.adownload_file("bucket", "object", max_bytes=limit)
            else:
                storage.download_file("bucket", "object", max_bytes=limit)
    else:
        if async_read:
            result = await storage.adownload_file("bucket", "object", max_bytes=limit)
        else:
            result = storage.download_file("bucket", "object", max_bytes=limit)
        assert result == content

    assert response.read_sizes == [limit + 1]
    assert response.bytes_read == min(len(content), limit + 1)
    assert response.closed is True
    assert response.released is True


@pytest.mark.asyncio
async def test_negative_object_read_limit_fails_before_opening_object():
    def fail_open(**_kwargs):
        raise AssertionError("invalid limit must not open object")

    storage = MinIOClient()
    storage._client = SimpleNamespace(get_object=fail_open)

    with pytest.raises(ValueError, match="non-negative"):
        await storage.adownload_file("bucket", "object", max_bytes=-1)


class _Response(BytesIO):
    """记录实际消费字节数与响应清理结果。"""

    def __init__(self, content, *, read_error=False):
        super().__init__(content)
        self.read_sizes = []
        self.bytes_read = 0
        self.read_error = read_error
        self.released = False

    def read(self, size=-1):
        self.read_sizes.append(size)
        if self.read_error:
            raise RuntimeError("read failed")
        content = super().read(size)
        self.bytes_read += len(content)
        return content

    def release_conn(self):
        self.released = True


@pytest.mark.asyncio
@pytest.mark.parametrize("async_read", [False, True])
@pytest.mark.parametrize("read_error", [False, True])
async def test_unbounded_object_download_always_releases_response(async_read, read_error):
    response = _Response(b"content", read_error=read_error)
    storage = MinIOClient()
    storage._client = SimpleNamespace(get_object=lambda **_kwargs: response)

    if read_error:
        with pytest.raises(RuntimeError, match="read failed"):
            if async_read:
                await storage.adownload_file("bucket", "object")
            else:
                storage.download_file("bucket", "object")
    elif async_read:
        assert await storage.adownload_file("bucket", "object") == b"content"
    else:
        assert storage.download_file("bucket", "object") == b"content"

    assert response.closed is True
    assert response.released is True
