import json
from io import BytesIO

import pytest
from minio.error import S3Error
from urllib3 import HTTPResponse
from yuxi.storage.minio.client import MinIOClient, StorageError, normalize_public_minio_url


class FakeMinio:
    def __init__(self):
        self.policy = None

    def bucket_exists(self, bucket_name: str) -> bool:
        return False

    def make_bucket(self, bucket_name: str) -> None:
        return None

    def set_bucket_policy(self, bucket_name: str, policy: str) -> None:
        self.policy = json.loads(policy)

    def put_object(self, **kwargs):
        return object()


def test_public_image_uses_same_origin_url_without_bucket_listing(monkeypatch):
    monkeypatch.setenv("MINIO_PUBLIC_URL", "/minio")
    client = MinIOClient()
    fake_minio = FakeMinio()
    client._client = fake_minio

    result = client.upload_file("public", "images/user 1/avatar.png", b"image", "image/png")

    assert result.url == "/minio/public/images/user%201/avatar.png"
    assert fake_minio.policy is not None
    actions = [action for statement in fake_minio.policy["Statement"] for action in statement["Action"]]
    assert actions == ["s3:GetObject"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "http://example.test:9000/public/avatar/user.png",
            "/minio/public/avatar/user.png",
        ),
        ("https://cdn.example.test/public/user.png", "https://cdn.example.test/public/user.png"),
        (
            "http://example.test:9000/public/avatar/user.png?v=123#preview",
            "/minio/public/avatar/user.png?v=123#preview",
        ),
    ],
)
def test_legacy_public_minio_url_is_normalized(monkeypatch, url, expected):
    monkeypatch.setenv("MINIO_PUBLIC_URL", "/minio")

    assert normalize_public_minio_url(url) == expected


@pytest.mark.parametrize("read_error", [False, True])
def test_download_file_always_releases_response(read_error):
    class Response:
        closed = False
        released = False

        def read(self):
            if read_error:
                raise RuntimeError("read failed")
            return b"content"

        def close(self):
            self.closed = True

        def release_conn(self):
            self.released = True

    response = Response()
    client = MinIOClient()
    client._client = type("FakeClient", (), {"get_object": lambda _self, **_kwargs: response})()

    if read_error:
        with pytest.raises(RuntimeError, match="read failed"):
            client.download_file("bucket", "object")
    else:
        assert client.download_file("bucket", "object") == b"content"

    assert response.closed is True
    assert response.released is True


@pytest.mark.asyncio
@pytest.mark.parametrize("read_error", [False, True])
async def test_async_download_file_always_releases_response(read_error):
    class Response:
        closed = False
        released = False

        def read(self):
            if read_error:
                raise RuntimeError("read failed")
            return b"content"

        def close(self):
            self.closed = True

        def release_conn(self):
            self.released = True

    response = Response()
    client = MinIOClient()
    client._client = type("FakeClient", (), {"get_object": lambda _self, **_kwargs: response})()

    if read_error:
        with pytest.raises(RuntimeError, match="read failed"):
            await client.adownload_file("bucket", "object")
    else:
        assert await client.adownload_file("bucket", "object") == b"content"

    assert response.closed is True
    assert response.released is True


@pytest.mark.asyncio
async def test_delete_prefix_is_idempotent_when_bucket_does_not_exist():
    client = MinIOClient()

    class MissingBucketClient:
        def list_objects(self, *_args, **_kwargs):
            response = HTTPResponse(BytesIO(b""), status=404)
            raise S3Error(response, "NoSuchBucket", "Not found", "kb-images", "request_id", "host_id")

    client._client = MissingBucketClient()

    assert await client.adelete_objects_by_prefix("kb-images", "kb-1/") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["NoSuchKey", "AccessDenied"])
async def test_optional_cache_download_only_allows_missing_object(code):
    """仅对象缺失可以返回空结果，权限等存储故障保持失败。"""
    client = MinIOClient()

    class FailingObject:
        """提供真实 SDK 错误码。"""

        def get_object(self, bucket_name, object_name):
            """模拟真实存储读取失败。"""
            raise S3Error(None, code, "test error", object_name, "test", "test")

    client._client = FailingObject()
    if code == "NoSuchKey":
        assert await client.adownload_file("bucket", "object", missing_ok=True) is None
    else:
        with pytest.raises(StorageError):
            await client.adownload_file("bucket", "object", missing_ok=True)
    with pytest.raises(StorageError):
        await client.adownload_file("bucket", "object")
