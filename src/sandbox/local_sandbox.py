import os
import subprocess
from pathlib import Path

from src.config.app import config
from src.sandbox.base import Sandbox
from src.sandbox.provider import SandboxProvider


class LocalSandbox(Sandbox):
    """
    纯本地无隔离沙盒实现（适用于 Windows/Mac 裸机开发）。
    直接使用 subprocess 在宿主机上执行指令，通过路径映射模拟隔离。
    """

    def __init__(self, id: str):
        super().__init__(id)
        base_dir = Path(config.save_dir).resolve() / "sandbox_data" / self.id
        self._workspace = str(base_dir)
        os.makedirs(self._workspace, exist_ok=True)

    def _resolve_path(self, path: str) -> str:
        """将沙盒内的虚拟路径映射到宿主机物理路径"""
        if os.path.isabs(path):
            rel = path.lstrip("/").lstrip("\\")
            # Windows：剥离盘符（如 C:）
            if len(rel) > 1 and rel[1] == ":":
                rel = rel[2:].lstrip("\\").lstrip("/")
            return str(Path(self._workspace) / rel)
        return str(Path(self._workspace) / path)

    def execute_command(self, command: str) -> str:
        try:
            # 兼容处理进程组分离，防止子进程结束/信号波及主 FastAPI 进程
            kw = {}
            if os.name == "nt":
                kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kw["start_new_session"] = True

            result = subprocess.run(
                command,
                shell=True,
                cwd=self._workspace,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=600,
                **kw
            )
            output = result.stdout
            if result.stderr:
                output += f"\nStd Error:\n{result.stderr}" if output else result.stderr
            if result.returncode != 0:
                output += f"\nExit Code: {result.returncode}"
            return output if output else "(无输出)"
        except subprocess.TimeoutExpired:
            return "Error: 执行超时 (超出 600s 时间限制)"
        except Exception as e:
            return f"Error: 执行异常 - {e}"

    def read_file(self, path: str) -> str:
        real_path = self._resolve_path(path)
        with open(real_path, encoding="utf-8") as f:
            return f.read()

    def list_dir(self, path: str) -> list[str]:
        """列出目录内容，最多 2 层"""
        real_path = self._resolve_path(path)
        results: list[str] = []
        if not os.path.isdir(real_path):
            raise FileNotFoundError(f"Directory not found: {path}")

        for entry in sorted(os.scandir(real_path), key=lambda e: e.name):
            prefix = "📁" if entry.is_dir() else "📄"
            results.append(f"{prefix} {entry.name}")
            # 第二层
            if entry.is_dir():
                try:
                    for sub in sorted(os.scandir(entry.path), key=lambda e: e.name):
                        sub_prefix = "📁" if sub.is_dir() else "📄"
                        results.append(f"  {sub_prefix} {entry.name}/{sub.name}")
                except PermissionError:
                    results.append(f"  ⛔ {entry.name}/ (permission denied)")
        return results

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        real_path = self._resolve_path(path)
        os.makedirs(os.path.dirname(real_path), exist_ok=True)
        mode = "a" if append else "w"
        with open(real_path, mode, encoding="utf-8") as f:
            f.write(content)


class LocalSandboxProvider(SandboxProvider):
    """Local Sandbox 提供者"""

    def __init__(self):
        self._sandboxes: dict[str, LocalSandbox] = {}

    def acquire(self, sandbox_id: str) -> Sandbox:
        if sandbox_id not in self._sandboxes:
            self._sandboxes[sandbox_id] = LocalSandbox(sandbox_id)
        return self._sandboxes[sandbox_id]

    def get(self, sandbox_id: str) -> Sandbox | None:
        return self._sandboxes.get(sandbox_id)

    def release(self, sandbox_id: str) -> None:
        # 本地模式保留文件方便调试，只从追踪中移除
        self._sandboxes.pop(sandbox_id, None)
