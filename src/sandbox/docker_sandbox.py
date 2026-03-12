import logging
import os
import tarfile
import time
from io import BytesIO

try:
    import docker
    from docker.errors import APIError
except ImportError:
    docker = None  # type: ignore[assignment]

from src.sandbox.base import Sandbox
from src.sandbox.provider import SandboxProvider

logger = logging.getLogger(__name__)


class DockerSandbox(Sandbox):
    """
    DooD (Docker-out-of-Docker) 安全隔离沙盒。
    通过挂载 docker.sock 在宿主 Docker 中创建临时容器执行指令。
    """

    def __init__(self, id: str, container):
        super().__init__(id)
        self.container = container

    def execute_command(self, command: str) -> str:
        try:
            exit_code, output = self.container.exec_run(
                cmd=["sh", "-c", command],
                workdir="/workspace",
            )
            res = output.decode("utf-8", errors="replace")
            if exit_code != 0:
                res += f"\nExit Code: {exit_code}"
            return res if res else "(无输出)"
        except Exception as e:
            return f"Error: 容器执行异常 - {e}"

    def read_file(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/workspace/{path}"
        try:
            bits, _ = self.container.get_archive(path)
            file_obj = BytesIO()
            for chunk in bits:
                file_obj.write(chunk)
            file_obj.seek(0)
            with tarfile.open(fileobj=file_obj) as tar:
                member = tar.next()
                if member and member.isfile():
                    f = tar.extractfile(member)
                    if f:
                        return f.read().decode("utf-8")
                raise FileNotFoundError(f"'{path}' is not a regular file inside sandbox.")
        except Exception as e:
            raise FileNotFoundError(f"Sandbox file '{path}' read error: {e}")

    def list_dir(self, path: str) -> list[str]:
        """通过 find 命令列出目录树（最多 2 层），解析输出为列表"""
        if not path.startswith("/"):
            path = f"/workspace/{path}"
        output = self.execute_command(f"find {path} -maxdepth 2 -not -path '*/\\.*' | head -200")
        if output.startswith("Error:"):
            raise FileNotFoundError(f"Directory not found: {path}")
        lines = [line for line in output.strip().split("\n") if line and line != path]
        return lines

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        if not path.startswith("/"):
            path = f"/workspace/{path}"

        dirname = os.path.dirname(path)
        filename = os.path.basename(path)

        if append:
            safe_content = content.replace("'", "'\\''")
            self.execute_command(f"mkdir -p {dirname} && printf '%s' '{safe_content}' >> {path}")
            return

        # 覆盖写入：使用 put_archive 安全传输，杜绝 Shell 转义漏洞
        self.execute_command(f"mkdir -p {dirname}")
        tar_stream = BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            content_bytes = content.encode("utf-8")
            tarinfo = tarfile.TarInfo(name=filename)
            tarinfo.size = len(content_bytes)
            tarinfo.mtime = int(time.time())
            tar.addfile(tarinfo=tarinfo, fileobj=BytesIO(content_bytes))
        tar_stream.seek(0)
        self.container.put_archive(dirname, tar_stream)


class DockerSandboxProvider(SandboxProvider):
    """通过 Docker daemon 管理沙盒容器的生命周期"""

    def __init__(self):
        if docker is None:
            raise ImportError(
                "docker Python 库未安装。请执行 'uv add docker' 或切换 sandbox_mode='local'"
            )
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            raise RuntimeError(f"无法连接 Docker daemon: {e}")

        self._sandboxes: dict[str, DockerSandbox] = {}
        self.sandbox_image = "python:3.10-slim"

    def _pull_image_if_not_present(self):
        try:
            self.client.images.get(self.sandbox_image)
        except docker.errors.ImageNotFound:
            logger.info(f"Pulling sandbox image '{self.sandbox_image}'...")
            self.client.images.pull(self.sandbox_image)

    def acquire(self, sandbox_id: str) -> Sandbox:
        if sandbox_id in self._sandboxes:
            return self._sandboxes[sandbox_id]

        self._pull_image_if_not_present()
        container_name = f"yuxi_sandbox_{sandbox_id}"

        # 清理可能残留的同名容器
        try:
            old = self.client.containers.get(container_name)
            old.remove(force=True)
            logger.info(f"Removed stale container: {container_name}")
        except docker.errors.NotFound:
            pass

        logger.info(f"Creating sandbox container for: {sandbox_id}")
        container = self.client.containers.run(
            self.sandbox_image,
            name=container_name,
            command="tail -f /dev/null",
            detach=True,
            network_mode="none",
            mem_limit="256m",
            nano_cpus=1_000_000_000,
            labels={"yuxi-know": "sandbox"},
            working_dir="/workspace",
        )

        sandbox = DockerSandbox(sandbox_id, container)
        self._sandboxes[sandbox_id] = sandbox
        return sandbox

    def get(self, sandbox_id: str) -> Sandbox | None:
        return self._sandboxes.get(sandbox_id)

    def release(self, sandbox_id: str) -> None:
        sandbox = self._sandboxes.pop(sandbox_id, None)
        if sandbox is not None:
            try:
                sandbox.container.remove(force=True)
                logger.info(f"Removed sandbox container: {sandbox_id}")
            except APIError as e:
                logger.error(f"Failed to remove sandbox container {sandbox_id}: {e}")
