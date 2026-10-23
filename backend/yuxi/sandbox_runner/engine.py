"""通过 Docker Engine API 访问 Unix socket 的最小客户端。"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from urllib.parse import quote

import httpx

MAX_FRAME_BYTES = 16 * 1024 * 1024
EXEC_STREAM_STDOUT = 1
EXEC_STREAM_STDERR = 2


class EngineError(RuntimeError):
    """保存 Docker/Podman 的受控错误消息与 HTTP 状态。"""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ExecDeadlineExceeded(EngineError):
    """exec 超过绝对墙钟期限；携带已收到输出供调用方返回。"""

    def __init__(self, output: bytes, truncated: bool):
        super().__init__("exec 超过执行期限")
        self.output = output
        self.truncated = truncated


class DockerEngine:
    """只实现 runner 需要的容器、exec、镜像与 archive 操作。"""

    def __init__(self, socket_path: str):
        """固定 Unix socket，不读取宿主环境代理。"""
        self.socket_path = socket_path

    def ping(self) -> str:
        """确认 daemon 可响应，不创建资源。"""
        with self._client(read_timeout=10) as client:
            response = client.get("/_ping")
            self._check(response)
            return response.text.strip()

    def version(self) -> dict:
        """读取 daemon 版本，用于健康输出。"""
        with self._client(read_timeout=10) as client:
            response = client.get("/version")
            self._check(response)
            return response.json()

    def image_identity(self, image: str) -> dict:
        """读取本地镜像 ID 与 RepoDigests；不触发拉取。"""
        with self._client(read_timeout=30) as client:
            response = client.get(f"/images/{quote(image, safe='')}/json")
            if response.status_code == 404:
                raise EngineError(f"镜像不存在：{image}", 404)
            self._check(response)
            payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("Id"), str):
            raise EngineError("镜像检查返回无效结果")
        digests = payload.get("RepoDigests")
        return {"id": payload["Id"], "repo_digests": digests if isinstance(digests, list) else []}

    def inspect_container(self, reference: str) -> dict | None:
        """读取容器事实；不存在返回 None。"""
        with self._client(read_timeout=30) as client:
            response = client.get(f"/containers/{quote(reference, safe='')}/json")
            if response.status_code == 404:
                return None
            self._check(response)
            payload = response.json()
        if not isinstance(payload, dict):
            raise EngineError("容器检查返回无效结果")
        return payload

    def list_containers(self, *, scope: str) -> list[dict]:
        """只列出当前部署的受管容器，包括已停止实例。"""
        filters = json.dumps({"label": ["yuxi.managed=true", f"yuxi.scope={scope}"]})
        with self._client(read_timeout=30) as client:
            response = client.get("/containers/json", params={"all": "1", "filters": filters})
            self._check(response)
            payload = response.json()
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise EngineError("容器列表返回无效结果")
        return payload

    def create_container(self, *, name: str, config: dict) -> dict:
        """按给定名称创建容器；名称冲突由调用方先检查。"""
        with self._client(read_timeout=120) as client:
            response = client.post("/containers/create", params={"name": name}, json=config)
            self._check(response)
            payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("Id"), str):
            raise EngineError("容器创建返回无效结果")
        return payload

    def start_container(self, container_id: str) -> None:
        """启动容器；已运行视为成功。"""
        with self._client(read_timeout=60) as client:
            response = client.post(f"/containers/{quote(container_id, safe='')}/start")
            if response.status_code == 304:
                return
            self._check(response)

    def remove_container(self, container_id: str) -> None:
        """强制删除容器；不存在视为成功。"""
        with self._client(read_timeout=60) as client:
            response = client.delete(
                f"/containers/{quote(container_id, safe='')}",
                params={"force": "1", "v": "1"},
            )
            if response.status_code == 404:
                return
            self._check(response)

    def create_exec(self, container_id: str, *, cmd: list[str], env: list[str], workdir: str, user: str) -> str:
        """创建非 TTY exec，输出保持 Docker 多路复用帧。"""
        body = {
            "Cmd": cmd,
            "Env": env,
            "WorkingDir": workdir,
            "User": user,
            "AttachStdout": True,
            "AttachStderr": True,
            "AttachStdin": False,
            "Tty": False,
        }
        with self._client(read_timeout=30) as client:
            response = client.post(f"/containers/{quote(container_id, safe='')}/exec", json=body)
            self._check(response)
            payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("Id"), str):
            raise EngineError("exec 创建返回无效结果")
        return payload["Id"]

    def start_exec(
        self,
        exec_id: str,
        *,
        read_timeout: float,
        output_budget: int,
        deadline: float | None = None,
    ) -> tuple[bytes, bool]:
        """读取 stdout/stderr 合并流；超预算继续排空，超过墙钟期限显式失败。"""
        output = bytearray()
        truncated = False
        decoder = _FrameDecoder()
        with self._client(read_timeout=read_timeout) as client:
            with client.stream(
                "POST",
                f"/exec/{quote(exec_id, safe='')}/start",
                json={"Detach": False, "Tty": False},
            ) as response:
                self._check(response)
                for chunk in response.iter_raw():
                    if deadline is not None and time.monotonic() >= deadline:
                        raise ExecDeadlineExceeded(bytes(output), truncated)
                    for payload in decoder.feed(chunk):
                        remaining = max(0, output_budget - len(output))
                        if remaining:
                            output.extend(payload[:remaining])
                        if len(payload) > remaining:
                            truncated = True
        decoder.finish()
        return bytes(output), truncated

    def inspect_exec(self, exec_id: str, *, timeout: float = 10) -> int:
        """轮询读取退出码，未取得终态则显式失败。"""
        deadline = time.monotonic() + timeout
        while True:
            with self._client(read_timeout=10) as client:
                response = client.get(f"/exec/{quote(exec_id, safe='')}/json")
                self._check(response)
                payload = response.json()
            if not isinstance(payload, dict):
                raise EngineError("exec 检查返回无效结果")
            exit_code = payload.get("ExitCode")
            if payload.get("Running") is False and isinstance(exit_code, int):
                return exit_code
            if time.monotonic() >= deadline:
                raise EngineError("exec 未取得可靠终态")
            time.sleep(0.05)

    def run_probe(
        self,
        container_id: str,
        *,
        cmd: list[str],
        env: list[str],
        workdir: str,
        user: str,
        timeout: float = 15,
        output_budget: int = 64 * 1024,
    ) -> tuple[int, str]:
        """执行 runner 自有短命令，返回退出码与合并输出。"""
        exec_id = self.create_exec(container_id, cmd=cmd, env=env, workdir=workdir, user=user)
        output, _ = self.start_exec(exec_id, read_timeout=timeout, output_budget=output_budget)
        return self.inspect_exec(exec_id, timeout=max(5, timeout)), output.decode("utf-8", errors="replace")

    def _client(self, *, read_timeout: float) -> httpx.Client:
        """每个请求独立客户端，避免跨线程共享连接状态。"""
        transport = httpx.HTTPTransport(uds=self.socket_path)
        return httpx.Client(
            transport=transport,
            base_url="http://docker",
            timeout=httpx.Timeout(connect=5, read=read_timeout, write=120, pool=5),
            trust_env=False,
        )

    @staticmethod
    def _check(response: httpx.Response) -> None:
        """把 daemon 错误转换为不含请求体的受控异常。"""
        if response.status_code < 400:
            return
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("message"), str):
                detail = payload["message"].strip()
        except (json.JSONDecodeError, ValueError):
            pass
        raise EngineError(detail[:300] or f"Docker API 返回 HTTP {response.status_code}", response.status_code)


class _FrameDecoder:
    """增量解析 Docker exec 的 8 字节头多路复用帧。"""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> Iterator[bytes]:
        """返回每个 stdout/stderr 负载，忽略其他流类型。"""
        self.buffer.extend(chunk)
        while len(self.buffer) >= 8:
            stream = self.buffer[0]
            size = int.from_bytes(self.buffer[4:8], "big")
            if size > MAX_FRAME_BYTES:
                raise EngineError("exec 输出帧超过限制")
            if len(self.buffer) < size + 8:
                break
            payload = bytes(self.buffer[8 : size + 8])
            del self.buffer[: size + 8]
            if stream in {EXEC_STREAM_STDOUT, EXEC_STREAM_STDERR}:
                yield payload

    def finish(self) -> None:
        """拒绝不完整帧，避免把断流当成完整输出。"""
        if self.buffer:
            raise EngineError("exec 输出流包含不完整帧")


__all__ = ["DockerEngine", "EngineError"]
