"""沙盒提供者工厂。"""

import logging
from abc import ABC, abstractmethod

from src.config.app import config
from src.sandbox.base import Sandbox

logger = logging.getLogger(__name__)


class SandboxProvider(ABC):
    """沙盒提供者抽象接口工厂"""

    @abstractmethod
    def acquire(self, sandbox_id: str) -> Sandbox:
        """分配/获取一个沙盒，如果不存在则创建

        Args:
            sandbox_id: 沙盒的唯一标识符（例如 Thread ID）

        Returns:
            Sandbox 实例
        """
        pass

    @abstractmethod
    def release(self, sandbox_id: str) -> None:
        """释放指定的临时沙盒环境，销毁与之对应的资源

        Args:
            sandbox_id: 沙盒的唯一标识符
        """
        pass

    @abstractmethod
    def get(self, sandbox_id: str) -> Sandbox | None:
        """获取当前已分配的沙盒

        Args:
            sandbox_id: 沙盒的唯一标识符
        """
        pass


_default_sandbox_provider: SandboxProvider | None = None


def get_sandbox_provider() -> SandboxProvider:
    """获取沙盒提供者工厂的单例

    会根据环境变量或者 config.sandbox_mode 的值决定使用何种底层的隔离环境。
    支持: 'local', 'docker', 'k8s'

    Returns:
        SandboxProvider 的具体实现实例
    """
    global _default_sandbox_provider
    if _default_sandbox_provider is None:
        mode = getattr(config, "sandbox_mode", "docker")

        if mode == "local":
            from src.sandbox.local_sandbox import LocalSandboxProvider

            _default_sandbox_provider = LocalSandboxProvider()
            logger.info("Initialized Local Sandbox Provider (No-isolation)")
        elif mode == "docker":
            from src.sandbox.docker_sandbox import DockerSandboxProvider

            _default_sandbox_provider = DockerSandboxProvider()
            logger.info("Initialized Docker Sandbox Provider (DooD)")
        elif mode == "k8s":
            from src.sandbox.k8s_sandbox import K8sSandboxProvider

            _default_sandbox_provider = K8sSandboxProvider()
            logger.info("Initialized K8s Sandbox Provider (Provisioner)")
        else:
            raise ValueError(f"Unknown sandbox mode: {mode}")

    return _default_sandbox_provider


def reset_sandbox_provider():
    """测试或重定位环境时重置单例"""
    global _default_sandbox_provider
    _default_sandbox_provider = None
