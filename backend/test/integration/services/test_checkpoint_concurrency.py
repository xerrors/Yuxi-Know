"""真实 PostgreSQL 验证不同构图不共用 saver 锁，且持久化不依赖实例缓存。"""

import asyncio
import os
import uuid
from typing import TypedDict

import pytest
from langgraph.graph import START, StateGraph
from psycopg_pool import AsyncConnectionPool
from yuxi.infrastructure.postgres.checkpointer import get_langgraph_checkpointer
from yuxi.infrastructure.postgres.manager import PostgresManager

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class CounterState(TypedDict):
    """不调用外部模型的确定性 checkpoint 状态。"""

    value: int


async def test_graphs_share_pool_not_lock_and_restore_independent_history(monkeypatch):
    """持有 A 锁时 B 仍能读取；新 saver 可恢复两条线程的历史与 pending writes。"""
    url = os.environ["POSTGRES_URL"].replace("+asyncpg", "").replace("+psycopg", "")
    async with (
        asyncio.timeout(15),
        AsyncConnectionPool(url, min_size=2, max_size=4, open=False, kwargs={"autocommit": True}) as pool,
    ):
        manager = object.__new__(PostgresManager)
        manager.__init__()
        manager._initialized = True
        manager.langgraph_pool = pool
        first = get_langgraph_checkpointer(manager)
        second = get_langgraph_checkpointer(manager)
        configs = [{"configurable": {"thread_id": f"pytest-checkpoint-{uuid.uuid4()}"}} for _ in range(2)]
        try:
            async with first.lock:
                assert await asyncio.wait_for(second.aget_tuple(configs[1]), timeout=2) is None

            builder = StateGraph(CounterState)
            builder.add_node("increment", lambda state: {"value": state["value"] + 1})
            builder.add_edge(START, "increment")
            builder.set_finish_point("increment")
            graphs = [builder.compile(checkpointer=saver) for saver in (first, second)]
            async with asyncio.TaskGroup() as tasks:
                runs = [
                    tasks.create_task(graph.ainvoke({"value": index * 10}, config))
                    for index, (graph, config) in enumerate(zip(graphs, configs, strict=True))
                ]
            assert [run.result() for run in runs] == [{"value": 1}, {"value": 11}]

            reader = get_langgraph_checkpointer(manager)
            for index, config in enumerate(configs):
                restored = await reader.aget_tuple(config)
                assert restored.checkpoint["channel_values"]["value"] == index * 10 + 1
                await first.aput_writes(restored.config, [("diagnostic", index)], f"task-{index}")
                reread = await reader.aget_tuple(config)
                assert (f"task-{index}", "diagnostic", index) in reread.pending_writes
                assert all(task != f"task-{1 - index}" for task, _, _ in reread.pending_writes)
        finally:
            async with asyncio.timeout(5):
                for config in configs:
                    await first.adelete_thread(config["configurable"]["thread_id"])
