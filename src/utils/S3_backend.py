"""
Deep Agents Remote Backends

S3 backend implementations for LangChain's Deep Agents.
Supports any S3-compatible storage (AWS S3, MinIO, etc.) 
with connection pooling for optimal performance.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import re
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, AsyncIterator, Coroutine

import aioboto3
import wcmatch.glob as wcglob
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from deepagents.backends.utils import (
    check_empty_content,
    format_content_with_line_numbers,
    perform_string_replacement,
)

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client

__all__ = ["S3Backend", "S3Config"]


def run_async_safely[T](coroutine: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: dict[str, T] = {}
    error: dict[str, Exception] = {}

    def _run() -> None:
        try:
            result["value"] = asyncio.run(coroutine)
        except Exception as exc:  # noqa: BLE001
            error["value"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise TimeoutError("Timed out while waiting for coroutine result")
    if "value" in error:
        raise error["value"]

    return result["value"]


# =============================================================================
# S3 Backend (S3-compatible: AWS S3, MinIO, etc.)
# =============================================================================


@dataclass
class S3Config:
    """Configuration for S3-compatible storage."""

    bucket: str
    prefix: str = ""
    region: str = "us-east-1"
    endpoint_url: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    use_ssl: bool = True
    max_pool_connections: int = 50
    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    max_retries: int = 3


class S3Backend(BackendProtocol):
    """
    S3-compatible backend for Deep Agents file operations.

    Supports AWS S3, MinIO, and any S3-compatible object storage.
    All operations are async-native using aioboto3.

    Files are stored as objects with paths mapping to S3 keys.
    Content is stored as JSON with the structure:
    {"content": [...lines], "created_at": "...", "modified_at": "..."}
    """

    def __init__(self, config: S3Config) -> None:
        self._config = config
        self._prefix = config.prefix.strip("/")
        if self._prefix:
            self._prefix += "/"

        self._boto_config = BotoConfig(
            region_name=config.region,
            signature_version="s3v4",
            retries={"max_attempts": config.max_retries, "mode": "adaptive"},
            max_pool_connections=config.max_pool_connections,
            connect_timeout=config.connect_timeout,
            read_timeout=config.read_timeout,
        )

        session_kwargs: dict[str, Any] = {}
        if config.access_key_id:
            session_kwargs["aws_access_key_id"] = config.access_key_id
        if config.secret_access_key:
            session_kwargs["aws_secret_access_key"] = config.secret_access_key

        self._session = aioboto3.Session(**session_kwargs)
        self._bucket = config.bucket

    def _s3_key(self, path: str) -> str:
        """Convert virtual path to S3 key."""
        clean = path.lstrip("/")
        return f"{self._prefix}{clean}"

    def _virtual_path(self, key: str) -> str:
        """Convert S3 key to virtual path."""
        if self._prefix and key.startswith(self._prefix):
            key = key[len(self._prefix) :]
        return "/" + key.lstrip("/")

    @asynccontextmanager
    async def _client(self) -> AsyncIterator["S3Client"]:
        """Get S3 client context."""
        async with self._session.client(
            "s3",
            config=self._boto_config,
            endpoint_url=self._config.endpoint_url,
            use_ssl=self._config.use_ssl,
        ) as client:
            yield client

    async def _get_file_data(self, path: str) -> dict[str, Any] | None:
        """Get file data dict from S3."""
        key = self._s3_key(path)
        try:
            async with self._client() as client:
                response = await client.get_object(Bucket=self._bucket, Key=key)
                async with response["Body"] as stream:
                    content = await stream.read()
                return json.loads(content.decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    async def _put_file_data(
        self, path: str, data: dict[str, Any], *, update_modified: bool = True
    ) -> None:
        """Put file data dict to S3."""
        key = self._s3_key(path)
        if update_modified:
            data["modified_at"] = datetime.now(timezone.utc).isoformat()
        content = json.dumps(data).encode("utf-8")
        async with self._client() as client:
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType="application/json",
            )

    async def _exists(self, path: str) -> bool:
        """Check if file exists in S3."""
        key = self._s3_key(path)
        try:
            async with self._client() as client:
                await client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    async def _list_keys(self, prefix: str = "") -> list[dict[str, Any]]:
        """List all keys with a prefix."""
        full_prefix = self._s3_key(prefix)
        results: list[dict[str, Any]] = []
        async with self._client() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self._bucket, Prefix=full_prefix
            ):
                for obj in page.get("Contents", []):
                    results.append(obj)
        return results

    # -------------------------------------------------------------------------
    # BackendProtocol Implementation
    # -------------------------------------------------------------------------

    def ls_info(self, path: str) -> list[FileInfo]:
        """Sync wrapper for als_info."""
        return run_async_safely(self.als_info(path))

    async def als_info(self, path: str) -> list[FileInfo]:
        """List files in a directory."""
        prefix = path.lstrip("/")
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        objects = await self._list_keys(prefix)
        results: list[FileInfo] = []
        seen_dirs: set[str] = set()

        for obj in objects:
            key = obj["Key"]
            vpath = self._virtual_path(key)

            # Check if this is a direct child or nested
            rel = vpath[len("/" + prefix) :] if prefix else vpath[1:]
            if "/" in rel:
                # This is in a subdirectory, add the directory entry
                dir_name = rel.split("/")[0]
                dir_path = "/" + prefix + dir_name + "/"
                if dir_path not in seen_dirs:
                    seen_dirs.add(dir_path)
                    results.append({"path": dir_path, "is_dir": True})
            else:
                # Direct file
                results.append(
                    {
                        "path": vpath,
                        "is_dir": False,
                        "size": obj.get("Size", 0),
                        "modified_at": obj["LastModified"].isoformat()
                        if "LastModified" in obj
                        else None,
                    }
                )

        results.sort(key=lambda x: x.get("path", ""))
        return results

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Sync wrapper for aread."""
        return run_async_safely(
            self.aread(file_path, offset, limit)
        )

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Read file content with line numbers."""
        data = await self._get_file_data(file_path)
        if data is None:
            return f"Error: File '{file_path}' not found"

        lines = data.get("content", [])
        if not lines:
            empty_msg = check_empty_content("")
            if empty_msg:
                return empty_msg

        if offset >= len(lines):
            return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"

        selected = lines[offset : offset + limit]
        return format_content_with_line_numbers(selected, start_line=offset + 1)

    def write(self, file_path: str, content: str) -> WriteResult:
        """Sync wrapper for awrite."""
        return run_async_safely(
            self.awrite(file_path, content)
        )

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        """Create a new file."""
        if await self._exists(file_path):
            return WriteResult(
                error=f"Cannot write to {file_path} because it already exists. "
                "Read and then make an edit, or write to a new path."
            )

        now = datetime.now(timezone.utc).isoformat()
        data = {
            "content": content.splitlines(),
            "created_at": now,
            "modified_at": now,
        }
        try:
            await self._put_file_data(file_path, data, update_modified=False)
            return WriteResult(path=file_path, files_update=None)
        except Exception as e:
            return WriteResult(error=f"Error writing file '{file_path}': {e}")

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Sync wrapper for aedit."""
        return run_async_safely(
            self.aedit(file_path, old_string, new_string, replace_all)
        )

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit file by replacing strings."""
        data = await self._get_file_data(file_path)
        if data is None:
            return EditResult(error=f"Error: File '{file_path}' not found")

        content = "\n".join(data.get("content", []))
        result = perform_string_replacement(content, old_string, new_string, replace_all)

        if isinstance(result, str):
            return EditResult(error=result)

        new_content, occurrences = result
        data["content"] = new_content.splitlines()

        try:
            await self._put_file_data(file_path, data)
            return EditResult(
                path=file_path, files_update=None, occurrences=int(occurrences)
            )
        except Exception as e:
            return EditResult(error=f"Error editing file '{file_path}': {e}")

    def grep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> list[GrepMatch] | str:
        """Sync wrapper for agrep_raw."""
        return run_async_safely(
            self.agrep_raw(pattern, path, glob)
        )

    async def agrep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> list[GrepMatch] | str:
        """Search for pattern in files."""
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        search_prefix = (path or "/").lstrip("/")
        objects = await self._list_keys(search_prefix)
        matches: list[GrepMatch] = []

        for obj in objects:
            vpath = self._virtual_path(obj["Key"])
            filename = PurePosixPath(vpath).name

            if glob and not wcglob.globmatch(filename, glob, flags=wcglob.BRACE):
                continue

            data = await self._get_file_data(vpath)
            if data is None:
                continue

            for line_num, line in enumerate(data.get("content", []), 1):
                if regex.search(line):
                    matches.append({"path": vpath, "line": line_num, "text": line})

        return matches

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Sync wrapper for aglob_info."""
        return run_async_safely(
            self.aglob_info(pattern, path)
        )

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Find files matching a glob pattern."""
        search_prefix = path.lstrip("/")
        objects = await self._list_keys(search_prefix)
        results: list[FileInfo] = []

        for obj in objects:
            vpath = self._virtual_path(obj["Key"])
            rel_path = vpath[len(path) :].lstrip("/") if path != "/" else vpath[1:]

            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(vpath, pattern):
                results.append(
                    {
                        "path": vpath,
                        "is_dir": False,
                        "size": obj.get("Size", 0),
                        "modified_at": obj["LastModified"].isoformat()
                        if "LastModified" in obj
                        else None,
                    }
                )

        results.sort(key=lambda x: x.get("path", ""))
        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Sync wrapper for aupload_files."""
        return run_async_safely(self.aupload_files(files))

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        """Upload multiple files."""
        responses: list[FileUploadResponse] = []
        async with self._client() as client:
            for path, content in files:
                try:
                    key = self._s3_key(path)
                    await client.put_object(
                        Bucket=self._bucket, Key=key, Body=content
                    )
                    responses.append(FileUploadResponse(path=path, error=None))
                except ClientError as e:
                    code = e.response["Error"]["Code"]
                    if code == "AccessDenied":
                        responses.append(
                            FileUploadResponse(path=path, error="permission_denied")
                        )
                    else:
                        responses.append(
                            FileUploadResponse(path=path, error="invalid_path")
                        )
                except Exception:
                    responses.append(
                        FileUploadResponse(path=path, error="invalid_path")
                    )
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Sync wrapper for adownload_files."""
        return run_async_safely(self.adownload_files(paths))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download multiple files."""
        responses: list[FileDownloadResponse] = []
        async with self._client() as client:
            for path in paths:
                try:
                    key = self._s3_key(path)
                    response = await client.get_object(Bucket=self._bucket, Key=key)
                    async with response["Body"] as stream:
                        content = await stream.read()
                    responses.append(
                        FileDownloadResponse(path=path, content=content, error=None)
                    )
                except ClientError as e:
                    code = e.response["Error"]["Code"]
                    if code == "NoSuchKey":
                        responses.append(
                            FileDownloadResponse(
                                path=path, content=None, error="file_not_found"
                            )
                        )
                    elif code == "AccessDenied":
                        responses.append(
                            FileDownloadResponse(
                                path=path, content=None, error="permission_denied"
                            )
                        )
                    else:
                        responses.append(
                            FileDownloadResponse(
                                path=path, content=None, error="invalid_path"
                            )
                        )
        return responses
