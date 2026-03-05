from __future__ import annotations

import base64
from pathlib import PurePosixPath
from typing import Any

from deepagents.backends.sandbox import BaseSandbox
from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse

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

    def _get_client(self):
        connection = self._provider.get(self._thread_id, create_if_missing=True)
        if connection is None:
            raise RuntimeError(f"sandbox is unavailable for thread {self._thread_id}")

        if self._client is None or self._client_url != connection.sandbox_url:
            self._client = self._build_client(connection.sandbox_url)
            self._client_url = connection.sandbox_url

        return self._client

    @staticmethod
    def _extract_data(payload: Any) -> Any:
        return getattr(payload, "data", payload)

    def _shell_exec(self, command: str):
        client = self._get_client()
        shell = getattr(client, "shell", None)
        if shell is not None:
            if hasattr(shell, "exec_command"):
                return shell.exec_command(command=command)
            if hasattr(shell, "exec"):
                return shell.exec(command=command)
        if hasattr(client, "exec_command"):
            return client.exec_command(command=command)
        raise RuntimeError("sandbox client does not provide shell execution API")

    def _write_binary(self, path: str, content: bytes) -> None:
        client = self._get_client()
        file_api = getattr(client, "file", None)
        if file_api is None:
            raise RuntimeError("sandbox client does not provide file API")

        encoded = base64.b64encode(content).decode("ascii")
        if hasattr(file_api, "write_file"):
            try:
                file_api.write_file(file=path, content=encoded, encoding="base64")
                return
            except TypeError:
                file_api.write_file(file=path, content=content.decode("utf-8", errors="replace"))
                return
        if hasattr(file_api, "write"):
            file_api.write(path=path, content=encoded, encoding="base64")
            return
        raise RuntimeError("sandbox file API does not provide write method")

    def _read_binary(self, path: str) -> bytes:
        client = self._get_client()
        file_api = getattr(client, "file", None)
        if file_api is None:
            raise RuntimeError("sandbox client does not provide file API")

        result: Any
        if hasattr(file_api, "read_file"):
            try:
                result = file_api.read_file(file=path, encoding="base64")
            except TypeError:
                result = file_api.read_file(file=path)
        elif hasattr(file_api, "read"):
            result = file_api.read(path=path, encoding="base64")
        else:
            raise RuntimeError("sandbox file API does not provide read method")

        data = self._extract_data(result)
        content = getattr(data, "content", None)
        if content is None and isinstance(data, dict):
            content = data.get("content")
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
        """Read file content directly via file API to avoid shell-output false positives."""
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

        return "\n".join(
            f"{start + idx + 1:6d}\t{line}"
            for idx, line in enumerate(selected_lines)
        )

    def execute(self, command: str) -> ExecuteResponse:
        try:
            result = self._shell_exec(command)
            data = self._extract_data(result)
            output = getattr(data, "output", None)
            if output is None and isinstance(data, dict):
                output = data.get("output")
            if output is None:
                output = str(data) if data is not None else ""
            if not isinstance(output, str):
                output = str(output)

            exit_code = getattr(data, "exit_code", None)
            if exit_code is None and isinstance(data, dict):
                exit_code = data.get("exit_code")
            if isinstance(exit_code, str) and exit_code.isdigit():
                exit_code = int(exit_code)

            truncated = bool(getattr(data, "truncated", False))
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

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                normalized_path = _normalize_path(path)
                self._write_binary(normalized_path, content)
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
