"""沙盒生命周期管理中间件。

职责单一：在 Agent 执行结束后（after_agent）释放本轮使用的沙盒资源。
沙盒的创建由 tools.py 中的 ensure_sandbox_initialized 按需触发，
Middleware 不需要提前分配，也不需要维护自己的状态。
"""

import logging

from langchain.agents.middleware import AgentMiddleware

from src.sandbox.provider import get_sandbox_provider

logger = logging.getLogger(__name__)


class SandboxMiddleware(AgentMiddleware):
    """沙盒生命周期管理中间件。

    与 deer-flow 保持一致的设计：
    - 工具在首次调用时通过 provider.acquire(thread_id) 懒初始化沙盒
    - provider 内部缓存保证同一 thread_id 只创建一次
    - 本中间件在 after_agent 阶段通过 thread_id 统一释放资源

    NOTE: 不需要自定义 State schema，因为沙盒 ID 就是 thread_id，
    可以直接从 runtime.context 中获取，无需额外的 state 追踪字段。
    """

    def after_agent(self, state, runtime) -> dict | None:
        """Agent 执行结束后释放沙盒资源"""
        thread_id = getattr(runtime.context, "thread_id", None)
        if thread_id is None:
            return None

        provider = get_sandbox_provider()
        sandbox = provider.get(thread_id)
        if sandbox is not None:
            provider.release(thread_id)
            logger.info(f"Released sandbox for thread: {thread_id}")

        return None
