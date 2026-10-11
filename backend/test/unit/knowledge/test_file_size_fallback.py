from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from test.unit.support.knowledge import FakeKnowledgeBase


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


@pytest.mark.unit
class TestAddFileRecordSizeFallback:
    """Test that add_file_record fills size from MinIO when not provided."""

    def _make_test_kb(self, work_dir="/tmp/test_kb"):
        kb = FakeKnowledgeBase(work_dir=work_dir)
        kb._persist_file_meta = AsyncMock()
        return kb

    @pytest.mark.asyncio
    async def test_add_file_record_fetches_size_from_minio_when_missing(self):
        kb = self._make_test_kb()

        item = "minio://knowledgebases/db1/upload/test_1234567890123.pdf"
        params = {
            "content_type": "file",
            "content_hashes": {item: "abc123"},
        }

        mock_minio = AsyncMock()
        mock_minio.astat_file.return_value = 9999

        with patch("yuxi.infrastructure.minio.get_minio_client", return_value=mock_minio):
            metadata = await kb.add_file_record(
                "db1",
                item,
                params=params,
                additional_params={},
            )

            assert metadata["size"] == 9999
            mock_minio.astat_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_file_record_keeps_provided_size(self):
        kb = self._make_test_kb()

        item = "minio://knowledgebases/db1/upload/test_1234567890123.pdf"
        params = {
            "content_type": "file",
            "content_hashes": {item: "abc123"},
            "file_sizes": {item: 5555},
        }

        mock_minio = AsyncMock()

        with patch("yuxi.infrastructure.minio.get_minio_client", return_value=mock_minio):
            metadata = await kb.add_file_record(
                "db1",
                item,
                params=params,
                additional_params={},
            )

            assert metadata["size"] == 5555
            mock_minio.astat_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_file_record_size_fallback_handles_error_gracefully(self):
        kb = self._make_test_kb()

        item = "minio://knowledgebases/db1/upload/test_1234567890123.pdf"
        params = {
            "content_type": "file",
            "content_hashes": {item: "abc123"},
        }

        mock_minio = AsyncMock()
        mock_minio.astat_file.side_effect = Exception("MinIO connection error")

        with patch("yuxi.infrastructure.minio.get_minio_client", return_value=mock_minio):
            metadata = await kb.add_file_record(
                "db1",
                item,
                params=params,
                additional_params={},
            )

            assert metadata.get("size") is None
