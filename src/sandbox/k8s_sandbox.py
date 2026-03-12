from __future__ import annotations

from src.config.app import config
from src.sandbox.base import Sandbox
from src.sandbox.provider import SandboxProvider
from src.sandbox.provisioner_client import ProvisionerClient
from src.sandbox.remote_sandbox_client import RemoteSandboxClient


class K8sSandbox(Sandbox):
    def __init__(
        self,
        id: str,
        base_url: str,
        client: RemoteSandboxClient,
    ):
        super().__init__(id)
        self.base_url = base_url
        self._client = client

    @staticmethod
    def _normalize_path(path: str) -> str:
        if path.startswith("/"):
            return path
        return f"/workspace/{path}"

    def execute_command(self, command: str) -> str:
        data = self._client.execute_command(command, cwd="/workspace")
        stdout = data.get("stdout") or ""
        stderr = data.get("stderr") or ""
        exit_code = data.get("exit_code", 0)

        output = stdout
        if stderr:
            output += f"\nStd Error:\n{stderr}" if output else stderr
        if exit_code != 0:
            output += f"\nExit Code: {exit_code}"
        return output if output else "(无输出)"

    def read_file(self, path: str) -> str:
        data = self._client.read_file(self._normalize_path(path))
        if data.get("is_dir"):
            raise IsADirectoryError(path)
        content = data.get("content")
        if content is None:
            raise FileNotFoundError(path)
        return content

    def list_dir(self, path: str) -> list[str]:
        data = self._client.list_dir(self._normalize_path(path))
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise FileNotFoundError(path)
        return [str(entry) for entry in entries]

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        data = self._client.write_file(self._normalize_path(path), content, append)
        if data.get("ok") is False:
            raise OSError(data.get("error") or f"Failed to write file: {path}")


class K8sSandboxProvider(SandboxProvider):
    def __init__(self):
        if not config.sandbox_k8s_provisioner_url:
            raise ValueError("SANDBOX_K8S_PROVISIONER_URL is required when sandbox_mode='k8s'")

        self._sandboxes: dict[str, K8sSandbox] = {}
        self._provisioner_client = ProvisionerClient(
            base_url=config.sandbox_k8s_provisioner_url,
            timeout_seconds=config.sandbox_k8s_request_timeout_seconds,
        )
        self._request_timeout_seconds = config.sandbox_k8s_request_timeout_seconds

    def acquire(self, sandbox_id: str) -> Sandbox:
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox is not None:
            return sandbox

        provisioned = self._provisioner_client.create_sandbox(sandbox_id)
        sandbox = K8sSandbox(
            id=sandbox_id,
            base_url=provisioned.base_url,
            client=RemoteSandboxClient(
                base_url=provisioned.base_url,
                timeout_seconds=self._request_timeout_seconds,
            ),
        )
        self._sandboxes[sandbox_id] = sandbox
        return sandbox

    def get(self, sandbox_id: str) -> Sandbox | None:
        return self._sandboxes.get(sandbox_id)

    def release(self, sandbox_id: str) -> None:
        sandbox = self._sandboxes.pop(sandbox_id, None)
        if sandbox is None:
            return
        self._provisioner_client.delete_sandbox(sandbox_id)
