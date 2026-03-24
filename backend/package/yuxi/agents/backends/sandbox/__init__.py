"""Yuxi Sandbox 子包。

此部分的实现重点参考了以下开源项目：
- deerflow: https://github.com/bytedance/deer-flow
- deepagents: https://github.com/langchain-ai/deepagents

包含沙盒的核心组件：
- sandbox_executor: 在容器内执行命令和文件操作的执行器
- sandbox_provisioner: 沙盒资源调配器，管理容器生命周期
- sandbox_provisioner_base: provisioner 的抽象基类
- sandbox_local_container: 本地 Docker 容器管理器
- sandbox_remote: 远程沙盒管理器（HTTP API）
- sandbox_config: 配置常量
- sandbox_info: 沙盒信息数据结构
- path_security: 路径安全检查
- docker_api: Docker API 调用封装
"""

from .sandbox_executor import YuxiSandboxBackend
from .sandbox_info import SandboxInfo
from .sandbox_provisioner import YuxiSandboxProvider, get_sandbox_provider
from .sandbox_provisioner_base import SandboxBackend
from .sandbox_config import (
    IDLE_CHECK_INTERVAL,
    LARGE_TOOL_RESULTS_DIR,
    OUTPUTS_DIR,
    SKILLS_PATH,
    THREADS_DIR,
    UPLOADS_DIR,
    USER_DATA_PATH,
    VIRTUAL_PATH_PREFIX,
    WORKSPACE_DIR,
    get_container_prefix,
    get_idle_timeout,
    get_max_replicas,
    get_sandbox_base_port,
    get_sandbox_host,
    get_sandbox_image,
    get_sandbox_provisioner_url,
    get_sandbox_security_opts,
)
from .sandbox_local_container import LocalContainerBackend
from .sandbox_remote import RemoteSandboxBackend
from .path_security import normalize_virtual_path

__all__ = [
    # Executor
    "YuxiSandboxBackend",
    # Provisioner
    "YuxiSandboxProvider",
    "get_sandbox_provider",
    # Provisioner base
    "SandboxBackend",
    # Local/Remote provisioner backends
    "LocalContainerBackend",
    "RemoteSandboxBackend",
    # Info
    "SandboxInfo",
    # Path security
    "normalize_virtual_path",
    # Config constants
    "VIRTUAL_PATH_PREFIX",
    "USER_DATA_PATH",
    "SKILLS_PATH",
    "WORKSPACE_DIR",
    "OUTPUTS_DIR",
    "UPLOADS_DIR",
    "LARGE_TOOL_RESULTS_DIR",
    "THREADS_DIR",
    "IDLE_CHECK_INTERVAL",
    "get_sandbox_image",
    "get_sandbox_base_port",
    "get_container_prefix",
    "get_idle_timeout",
    "get_max_replicas",
    "get_sandbox_host",
    "get_sandbox_provisioner_url",
    "get_sandbox_security_opts",
]
