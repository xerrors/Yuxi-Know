from __future__ import annotations

import base64
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from deepagents.backends.protocol import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from deepagents.backends.sandbox import BaseSandbox

from src import config as conf
from src.utils.logging_config import logger

from .provider import get_sandbox_provider, sandbox_id_for_thread


def _normalize_path(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("path is required")
    normalized = "/" + raw.lstrip("/")
    pure = PurePosixPath(normalized)
    if ".." in pure.parts:
        raise ValueError("path traversal is not allowed")
    return str(pure)


class ProvisionerSandboxBackend(BaseSandbox):
    def __init__(self, thread_id: str):
        self._thread_id = str(thread_id or "").strip()
        if not self._thread_id:
            raise ValueError("thread_id is required for ProvisionerSandboxBackend")

        self._provider = get_sandbox_provider()
        self._id = sandbox_id_for_thread(self._thread_id)
        self._client: Any | None = None
        self._client_url: str | None = None
        self._command_timeout_seconds = int(getattr(conf, "sandbox_exec_timeout_seconds", 180))
        self._max_output_bytes = int(getattr(conf, "sandbox_max_output_bytes", 262_144))

    @property
    def id(self) -> str:
        return self._id

    def _build_client(self, sandbox_url: str):
        try:
            from agent_sandbox import Sandbox as AgentSandboxClient
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "agent-sandbox is required. Install dependency `agent-sandbox` in the docker image."
            ) from exc

        return AgentSandboxClient(base_url=sandbox_url, timeout=self._command_timeout_seconds)

    def _get_client(self) -> Any:
        connection = self._provider.get(self._thread_id, create_if_missing=True)
        if connection is None:
            raise RuntimeError(f"sandbox is unavailable for thread {self._thread_id}")

        if self._client is None or self._client_url != connection.sandbox_url:
            self._client = self._build_client(connection.sandbox_url)
            self._client_url = connection.sandbox_url

        return self._client

    def _read_binary(self, path: str) -> bytes:
        """Read file content from the sandbox file API and normalize it to bytes.

        The underlying API may return base64 text, raw bytes, or plain strings.
        This helper is the single normalization point used by read(), edit(), and
        download_files() so all read paths share the same transport semantics.
        """
        result = self._get_client().file.read_file(file=path, encoding="base64")

        content = result.content
        if content is None:
            return b""
        if isinstance(content, bytes):
            return content
        if not isinstance(content, str):
            return str(content).encode("utf-8")

        try:
            return base64.b64decode(content, validate=True)
        except Exception:  # noqa: BLE001
            return content.encode("utf-8")

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read file content via the sandbox file API and render a text view.

        This stays on top of _read_binary() so the backend has one consistent
        read path for base64 transport, raw bytes, and text-like responses.
        """
        normalized_path = _normalize_path(file_path)
        start = max(0, int(offset))
        size = max(0, int(limit))

        try:
            content = self._read_binary(normalized_path)
        except Exception:  # noqa: BLE001
            return f"Error: File '{file_path}' not found"

        if not content:
            return "System reminder: File exists but has empty contents"

        text = content.decode("utf-8", errors="replace")
        lines = text.splitlines()
        selected_lines = lines[start : start + size]

        if not selected_lines:
            return ""

        return "\n".join(f"{start + idx + 1:6d}\t{line}" for idx, line in enumerate(selected_lines))

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Execute a shell command in the sandbox.

        Output is normalized to text and truncated to the configured maximum
        payload size before being returned.
        """
        try:
            kwargs: dict[str, Any] = {"command": command}
            if timeout is not None:
                kwargs["timeout"] = timeout
            result = self._get_client().shell.exec_command(**kwargs)

            output = getattr(result, "output", None)
            if output is None and isinstance(result, dict):
                output = result.get("output")
            if output is None:
                output = str(result) if result is not None else ""
            if not isinstance(output, str):
                output = str(output)

            exit_code = getattr(result, "exit_code", None)
            if exit_code is None and isinstance(result, dict):
                exit_code = result.get("exit_code")
            if isinstance(exit_code, str) and exit_code.isdigit():
                exit_code = int(exit_code)

            truncated = False
            encoded = output.encode("utf-8", errors="ignore")
            if len(encoded) > self._max_output_bytes:
                output = encoded[: self._max_output_bytes].decode("utf-8", errors="ignore")
                truncated = True

            return ExecuteResponse(
                output=output,
                exit_code=exit_code if isinstance(exit_code, int) else None,
                truncated=truncated,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Sandbox execute failed for thread {self._thread_id}: {exc}")
            return ExecuteResponse(output=f"Error: {exc}", exit_code=1, truncated=False)

    def ls_info(self, path: str) -> list[FileInfo]:
        """List direct children of a sandbox path with lightweight metadata."""
        normalized_path = _normalize_path(path)
        try:
            result = self._get_client().file.list_path(path=normalized_path, recursive=False, include_size=True)
        except Exception:  # noqa: BLE001
            return []

        entries = result.files or []
        infos: list[FileInfo] = []
        for entry in entries:
            info: FileInfo = {"path": entry.path, "is_dir": entry.is_directory}
            size = entry.size
            if isinstance(size, int):
                info["size"] = size
            modified_time = entry.modified_time
            if isinstance(modified_time, str) and modified_time:
                try:
                    info["modified_at"] = datetime.fromisoformat(modified_time).isoformat()
                except ValueError:
                    info["modified_at"] = modified_time
            infos.append(info)
        return infos

    def write(self, file_path: str, content: str) -> WriteResult:
        """Write a new text file.

        This method is intentionally text-only. Binary payloads should go through
        upload_files(), which uses base64 encoding for the sandbox file API.
        """
        normalized_path = _normalize_path(file_path)
        if not isinstance(content, str):
            return WriteResult(error="Error: write() only supports text content; use upload_files() for binary data")
        try:
            self._read_binary(normalized_path)
        except Exception:  # noqa: BLE001
            pass
        else:
            return WriteResult(error=f"Error: File '{file_path}' already exists")

        try:
            self._get_client().file.write_file(file=normalized_path, content=content)
        except Exception as exc:  # noqa: BLE001
            return WriteResult(error=str(exc) or f"Failed to write file '{file_path}'")

        return WriteResult(path=normalized_path, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        """Edit an existing text file by replacing string content.

        This method operates on UTF-8-decoded text content only. Binary files
        are not supported here and should be handled via download/upload flows.
        """
        normalized_path = _normalize_path(file_path)
        try:
            text = self._read_binary(normalized_path).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return EditResult(error=f"Error: File '{file_path}' not found")

        count = text.count(old_string)
        if count == 0:
            return EditResult(error=f"Error: String not found in file: '{old_string}'")
        if count > 1 and not replace_all:
            return EditResult(
                error=(
                    f"Error: String '{old_string}' appears multiple times. "
                    "Use replace_all=True to replace all occurrences."
                )
            )

        updated = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)

        try:
            self._get_client().file.write_file(file=normalized_path, content=updated)
        except Exception as exc:  # noqa: BLE001
            return EditResult(error=f"Error editing file (exit code 1): {exc or 'Unknown error'}")

        return EditResult(path=normalized_path, files_update=None, occurrences=count if replace_all else 1)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Search file contents under a path and return raw line matches.

        The sandbox file API is used directly with fixed-string matching and an
        optional include glob.
        """
        search_path = _normalize_path(path or "/")
        include = [glob] if glob else None

        try:
            result = self._get_client().file.grep_files(
                path=search_path,
                pattern=pattern,
                include=include,
                fixed_strings=True,
                recursive=True,
            )
        except Exception as exc:  # noqa: BLE001
            return str(exc)

        matches_out: list[GrepMatch] = []
        for match in result.matches or []:
            matches_out.append(
                {
                    "path": match.file,
                    "line": match.line_number,
                    "text": match.line_content,
                }
            )
        return matches_out

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Return files matching a glob pattern with optional metadata."""
        normalized_path = _normalize_path(path)

        try:
            result = self._get_client().file.glob_files(
                path=normalized_path,
                pattern=pattern,
                include_metadata=True,
            )
        except Exception:  # noqa: BLE001
            return []

        infos: list[FileInfo] = []
        for entry in result.files or []:
            info: FileInfo = {"path": entry.path}
            if isinstance(entry.is_directory, bool):
                info["is_dir"] = entry.is_directory
            if isinstance(entry.size, int):
                info["size"] = entry.size
            if isinstance(entry.modified_time, str) and entry.modified_time:
                try:
                    info["modified_at"] = datetime.fromisoformat(entry.modified_time).isoformat()
                except ValueError:
                    info["modified_at"] = entry.modified_time
            infos.append(info)
        return infos

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload binary or text file payloads via the sandbox file API.

        Contents are base64-encoded before calling the remote write_file API so
        arbitrary bytes can be transferred safely.
        """
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                normalized_path = _normalize_path(path)
                self._get_client().file.write_file(
                    file=normalized_path,
                    content=base64.b64encode(content).decode("ascii"),
                    encoding="base64",
                )
                responses.append(FileUploadResponse(path=normalized_path, error=None))
            except PermissionError:
                normalized_path = str(path)
                responses.append(FileUploadResponse(path=normalized_path, error="permission_denied"))
            except IsADirectoryError:
                normalized_path = str(path)
                responses.append(FileUploadResponse(path=normalized_path, error="is_directory"))
            except FileNotFoundError:
                normalized_path = str(path)
                responses.append(FileUploadResponse(path=normalized_path, error="file_not_found"))
            except Exception as exc:  # noqa: BLE001
                normalized_path = str(path)
                logger.warning(f"Upload to sandbox failed for {normalized_path}: {exc}")
                responses.append(FileUploadResponse(path=normalized_path, error="invalid_path"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download file payloads as raw bytes from the sandbox file API.

        The underlying API is read with base64 encoding and decoded back into
        bytes by _read_binary().
        """
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                normalized_path = _normalize_path(path)
                content = self._read_binary(normalized_path)
                responses.append(FileDownloadResponse(path=normalized_path, content=content, error=None))
            except PermissionError:
                normalized_path = str(path)
                responses.append(FileDownloadResponse(path=normalized_path, content=None, error="permission_denied"))
            except IsADirectoryError:
                normalized_path = str(path)
                responses.append(FileDownloadResponse(path=normalized_path, content=None, error="is_directory"))
            except FileNotFoundError:
                normalized_path = str(path)
                responses.append(FileDownloadResponse(path=normalized_path, content=None, error="file_not_found"))
            except Exception as exc:  # noqa: BLE001
                normalized_path = str(path)
                logger.warning(f"Download from sandbox failed for {normalized_path}: {exc}")
                responses.append(FileDownloadResponse(path=normalized_path, content=None, error="invalid_path"))
        return responses
