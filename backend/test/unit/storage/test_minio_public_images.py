import json
from io import BytesIO

import pytest
from minio.error import S3Error
from urllib3 import HTTPResponse

from yuxi.infrastructure.minio.client import MinIOClient, normalize_public_minio_url


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


@pytest.mark.asyncio
async def test_delete_prefix_is_idempotent_when_bucket_does_not_exist():
    client = MinIOClient()

    class MissingBucketClient:
        def list_objects(self, *_args, **_kwargs):
            response = HTTPResponse(BytesIO(b""), status=404)
            raise S3Error(response, "NoSuchBucket", "Not found", "kb-images", "request_id", "host_id")

    client._client = MissingBucketClient()

    assert await client.adelete_objects_by_prefix("kb-images", "kb-1/") == 0
