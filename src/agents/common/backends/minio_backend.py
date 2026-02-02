"""MinIO 虚拟文件系统后端 - 实现 BackendProtocol 接口"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from deepagents.backends.protocol import BackendProtocol, EditResult, WriteResult
from deepagents.backends.utils import FileInfo, GrepMatch

from src.utils import logger

if TYPE_CHECKING:
    from src.storage.minio.client import MinIOClient


class MinIOBackend(BackendProtocol):
    """基于 MinIO 的虚拟文件系统后端，用于存储对话附件。

    将 /attachments/{thread_id}/{file_id}.md 路径映射到 MinIO 的
    attachments/{thread_id}/{file_id}.md 对象存储。

    特点：
    - 附件内容持久化存储在 MinIO
    - 无需本地物理存储空间
    - 支持 Agent 的 read_file 工具读取
    """

    def __init__(
        self,
        bucket_name: str = "chat-attachments",
        minio_client: Optional[MinIOClient] = None,
    ):
        self.bucket_name = bucket_name
        self._client = minio_client

    @property
    def client(self) -> MinIOClient:
        """获取 MinIO 客户端实例"""
        if self._client is None:
            from src.storage.minio.client import MinIOClient

            self._client = MinIOClient()
        return self._client

    def _key(self, path: str) -> str:
        """将虚拟路径转换为 MinIO object key。

        虚拟路径: /attachments/{thread_id}/{file_id}.md
        MinIO key: attachments/{thread_id}/{file_id}.md
        """
        return path.lstrip("/")

    def _parse_path(self, path: str) -> tuple[Optional[str], Optional[str]]:
        """解析路径，提取 thread_id 和 filename。

        支持两种格式：
        - 目录路径: /attachments/{thread_id}/
        - 文件路径: /attachments/{thread_id}/{file_id}.md

        Returns:
            tuple[thread_id, filename] 或 (thread_id, None) 对于目录
        """
        # /attachments/{thread_id}/{file_id}.md -> parts = ['attachments', '{thread_id}', '{file_id}.md']
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            thread_id = parts[1]
            filename = parts[2] if len(parts) >= 3 else None
            return thread_id, filename
        return None, None

    def _ensure_bucket_exists(self) -> None:
        """确保存储桶存在"""
        self.client.ensure_bucket_exists(self.bucket_name)

    def _ensure_attachments_prefix(self, path: str) -> str:
        """确保路径以 /attachments/ 前缀开头。

        当此 backend 被 CompositeBackend 用于 /attachments/ 路由时，
        CompositeBackend 会剥离前缀，需要在此处补全。
        """
        if not path.startswith("/attachments/"):
            return f"/attachments/{path.lstrip('/')}"
        return path

    # ========== BackendProtocol 接口实现 ==========

    def ls_info(self, path: str) -> list[FileInfo]:
        """列出目录内容。

        Args:
            path: 虚拟路径，支持：
                - / - 返回 /attachments/ 目录（当此 backend 用于 /attachments/ 路由时）
                - /attachments/ - 列出所有 thread_id 目录
                - /attachments/{thread_id}/ - 列出某个 thread 的附件

        Returns:
            FileInfo 列表
        """
        # 确保路径有 /attachments/ 前缀（CompositeBackend 可能会剥离）
        path = self._ensure_attachments_prefix(path)

        # 处理根目录 - 当 CompositeBackend 将 /attachments/ 路由转换为 / 时
        if path == "/":
            # 对于根目录，返回 /attachments/ 作为入口点
            return [
                FileInfo(
                    path="/attachments/",
                    is_dir=True,
                    size=0,
                    modified_at=None,
                )
            ]

        if not path.startswith("/attachments/"):
            return []

        # 解析路径
        parts = path.strip("/").split("/")
        if len(parts) == 1:
            # /attachments/ - 列出所有 thread_id 目录
            prefix = "attachments/"
            try:
                self._ensure_bucket_exists()
                mc = self.client.client
                result: list[FileInfo] = []
                # 列出所有对象，按 thread_id 分组
                all_objects = list(mc.list_objects(self.bucket_name, prefix=prefix, recursive=False))
                seen_threads: set[str] = set()
                for obj in all_objects:
                    # 从 attachments/{thread_id}/{file_id}.md 中提取 thread_id
                    obj_parts = obj.object_name.strip("/").split("/")
                    if len(obj_parts) >= 2:
                        thread_id = obj_parts[1]
                        if thread_id not in seen_threads:
                            seen_threads.add(thread_id)
                            # 创建目录条目（虚拟的，不是真实目录）
                            result.append(
                                FileInfo(
                                    path=f"/attachments/{thread_id}/",
                                    is_dir=True,
                                    size=0,
                                    modified_at=obj.last_modified.isoformat() if obj.last_modified else None,
                                )
                            )
                return result
            except Exception as e:
                logger.error(f"MinIOBackend.ls_info failed for {path}: {e}")
                return []

        # /attachments/{thread_id}/ - 列出某个 thread 的附件
        thread_id, _ = self._parse_path(path)
        if not thread_id:
            return []

        prefix = f"attachments/{thread_id}/"
        try:
            self._ensure_bucket_exists()
            mc = self.client.client
            result: list[FileInfo] = []
            objects = list(mc.list_objects(self.bucket_name, prefix=prefix, recursive=False))
            for obj in objects:
                file_path = f"/{obj.object_name}"
                modified_at = obj.last_modified.isoformat() if obj.last_modified else None
                result.append(
                    FileInfo(
                        path=file_path,
                        is_dir=False,
                        size=obj.size,
                        modified_at=modified_at,
                    )
                )
            return result
        except Exception as e:
            logger.error(f"MinIOBackend.ls_info failed for {path}: {e}")
            return []

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """读取文件内容。

        Args:
            file_path: 虚拟路径，如 /attachments/{thread_id}/{file_id}.md
            offset: 起始行偏移
            limit: 最大行数

        Returns:
            带行号的内容字符串
        """
        # 确保路径有 /attachments/ 前缀（CompositeBackend 可能会剥离）
        file_path = self._ensure_attachments_prefix(file_path)

        if not file_path.startswith("/attachments/"):
            return f"Error: Access denied to {file_path}"

        _, filename = self._parse_path(file_path)
        if not filename:
            return f"Error: File not found: {file_path}"

        try:
            data = self.client.download_file(self.bucket_name, self._key(file_path))
            content = data.decode("utf-8")
            lines = content.split("\n")
            # 添加行号
            start = max(0, offset)
            end = start + limit
            numbered_lines = [f"{i+1}:{line}" for i, line in enumerate(lines[start:end], start + 1)]
            return "\n".join(numbered_lines)
        except Exception as e:
            logger.error(f"MinIOBackend.read failed for {file_path}: {e}")
            return f"Error reading {file_path}: {e}"

    def write(self, file_path: str, content: str) -> WriteResult:
        """写入文件（同步）。

        Args:
            file_path: 虚拟路径
            content: 文件内容

        Returns:
            WriteResult
        """
        # 确保路径有 /attachments/ 前缀
        file_path = self._ensure_attachments_prefix(file_path)

        if not file_path.startswith("/attachments/"):
            return WriteResult(error=f"Access denied: {file_path}")

        try:
            self._ensure_bucket_exists()
            data = content.encode("utf-8")
            self.client.upload_file(
                self.bucket_name,
                self._key(file_path),
                data,
                content_type="text/markdown",
            )
            logger.info(f"MinIOBackend: wrote {file_path}")
            return WriteResult(path=file_path, files_update=None)
        except Exception as e:
            logger.error(f"MinIOBackend.write failed for {file_path}: {e}")
            return WriteResult(error=str(e))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        """异步写入文件。

        Args:
            file_path: 虚拟路径
            content: 文件内容

        Returns:
            WriteResult
        """
        # 委托给同步 write 方法
        return self.write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """编辑文件。

        MinIO 后端不支持原地编辑，返回错误提示。
        """
        return EditResult(error="Edit not supported for MinIO backend")

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """glob 模式匹配。

        Args:
            pattern: glob 模式，如 *.md
            path: 搜索路径

        Returns:
            匹配的 FileInfo 列表
        """
        import fnmatch

        files = self.ls_info(path)
        result: list[FileInfo] = []
        for f in files:
            if fnmatch.fnmatch(f.path, pattern):
                result.append(f)
        return result

    def grep_raw(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
    ) -> list[GrepMatch] | str:
        """搜索文件内容。

        当前实现为简化版本，仅列出文件不进行实际搜索。
        """
        # 简化实现：暂不支持内容搜索
        logger.debug(f"MinIOBackend.grep_raw called with pattern={pattern}, path={path}")
        return []


def init_attachment_bucket() -> None:
    """初始化附件存储桶。

    在应用启动时调用，确保 chat-attachments 存储桶存在。
    """
    try:
        client = MinIOBackend()
        client._ensure_bucket_exists()
        logger.info("chat-attachments bucket initialized")
    except Exception as e:
        logger.error(f"Failed to initialize attachment bucket: {e}")
