from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestMinIOClientStatFile:
    """Test MinIOClient.stat_file and astat_file methods."""

    def test_stat_file_returns_size(self):
        from yuxi.infrastructure.minio.client import MinIOClient

        client = MinIOClient()
        mock_stat = MagicMock()
        mock_stat.size = 1024
        client._client = MagicMock()
        client._client.stat_object.return_value = mock_stat

        result = client.stat_file("knowledgebases", "db/upload/test.pdf")
        assert result == 1024
        client._client.stat_object.assert_called_once_with(bucket_name="knowledgebases", object_name="db/upload/test.pdf")

    def test_stat_file_returns_none_when_not_found(self):
        from io import BytesIO

        from minio.error import S3Error
        from urllib3 import HTTPResponse

        from yuxi.infrastructure.minio.client import MinIOClient

        client = MinIOClient()
        client._client = MagicMock()
        resp = HTTPResponse(BytesIO(b""), status=404)
        client._client.stat_object.side_effect = S3Error(resp, "NoSuchKey", "Not found", "resource", "request_id", "host_id")

        result = client.stat_file("knowledgebases", "db/upload/missing.pdf")
        assert result is None

    @pytest.mark.asyncio
    async def test_astat_file_returns_size(self):
        from yuxi.infrastructure.minio.client import MinIOClient

        client = MinIOClient()
        mock_stat = MagicMock()
        mock_stat.size = 2048
        client._client = MagicMock()
        client._client.stat_object.return_value = mock_stat

        result = await client.astat_file("knowledgebases", "db/upload/test.pdf")
        assert result == 2048
