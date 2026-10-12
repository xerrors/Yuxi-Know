"""用真实 PostgreSQL checkpoint 验证 Steer 的工具批次交接。"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass

import pytest
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from psycopg_pool import AsyncConnectionPool
from yuxi.modules.agents.runtime.middlewares.steer import SteerMiddleware
import yuxi.modules.agents.services.runs as runs
from yuxi.infrastructure.postgres.manager import PostgresManager
from yuxi.infrastructure.postgres.checkpointer import get_langgraph_checkpointer

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class _BoundaryModel(BaseChatModel):
    """首轮调用并行工具，续接时只读取已有结果。"""

    call_count: int = 0

    @property
    def _llm_type(self) -> str:
        """返回确定性模型标识。"""
        return "steer-checkpoint-boundary"

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        """保留工具调用由测试模型生成。"""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        """首轮请求工具，续接时核对完整模型上下文。"""
        self.call_count += 1
        if self.call_count == 1:
            message = AIMessage(
                content="",
                tool_calls=[
                    {"id": "first", "name": "first_tool", "args": {}},
                    {"id": "second", "name": "second_tool", "args": {}},
                ],
            )
        else:
            results = {item.tool_call_id: item.content for item in messages if isinstance(item, ToolMessage)}
            assert results == {"first": "first-result", "second": "second-result"}
            assert any(isinstance(item, HumanMessage) and item.content == "STEER" for item in messages)
            message = AIMessage(content="STEER_COMPLETE")
        return ChatResult(generations=[ChatGeneration(message=message)])


@dataclass
class _RunContext:
    """向真实 SteerMiddleware 提供当前 Run 身份。"""

    run_id: str


async def test_steer_waits_for_parallel_tools_and_next_run_reads_pg_checkpoint(monkeypatch: pytest.MonkeyPatch):
    """首个工具结束不能接管；续接读取完整 checkpoint 且不重复工具副作用。"""
    first_done = asyncio.Event()
    second_started = asyncio.Event()
    release_second = asyncio.Event()
    pending_steer = False
    effects: list[str] = []

    async def should_end(run_id: str) -> bool:
        """模拟持久队列中待领取的 steer。"""
        assert run_id in {"first-run", "next-run"}
        return pending_steer

    monkeypatch.setattr(runs, "should_yield_for_steer", should_end)

    @tool
    async def first_tool() -> str:
        """记录第一个工具的外部效果。"""
        effects.append("first")
        first_done.set()
        return "first-result"

    @tool
    async def second_tool() -> str:
        """等待测试释放第二个工具。"""
        second_started.set()
        await release_second.wait()
        effects.append("second")
        return "second-result"

    manager = object.__new__(PostgresManager)
    manager.__init__()
    url = os.environ["POSTGRES_URL"].replace("+asyncpg", "").replace("+psycopg", "")
    thread_id = f"pytest-steer-boundary-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}
    model = _BoundaryModel()

    async with (
        asyncio.timeout(20),
        AsyncConnectionPool(url, min_size=1, max_size=3, open=False, kwargs={"autocommit": True}) as pool,
    ):
        manager._initialized = True
        manager.langgraph_pool = pool
        saver = get_langgraph_checkpointer(manager)
        agent = create_agent(
            model=model,
            tools=[first_tool, second_tool],
            middleware=[SteerMiddleware()],
            context_schema=_RunContext,
            checkpointer=saver,
        )

        async def run_first() -> None:
            """消费首段执行的所有图事件。"""
            async for _ in agent.astream(
                {"messages": [HumanMessage("执行工具")]},
                config=config,
                context=_RunContext(run_id="first-run"),
                stream_mode="updates",
            ):
                pass

        task = asyncio.create_task(run_first())
        try:
            await asyncio.wait_for(second_started.wait(), timeout=5)
            await asyncio.wait_for(first_done.wait(), timeout=5)
            pending_steer = True
            assert not task.done()
            assert effects == ["first"]

            release_second.set()
            await asyncio.wait_for(task, timeout=5)
            assert model.call_count == 1

            restored = await get_langgraph_checkpointer(manager).aget_tuple(config)
            assert restored is not None
            tool_results = {
                message.tool_call_id: message.content
                for message in restored.checkpoint["channel_values"]["messages"]
                if isinstance(message, ToolMessage)
            }
            assert tool_results == {"first": "first-result", "second": "second-result"}

            pending_steer = False
            await agent.ainvoke(
                {"messages": [HumanMessage("STEER")]},
                config=config,
                context=_RunContext(run_id="next-run"),
            )
            final = await get_langgraph_checkpointer(manager).aget_tuple(config)
            assert final.checkpoint["channel_values"]["messages"][-1].content == "STEER_COMPLETE"
            assert effects == ["first", "second"]
            assert model.call_count == 2
        finally:
            release_second.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await saver.adelete_thread(thread_id)
