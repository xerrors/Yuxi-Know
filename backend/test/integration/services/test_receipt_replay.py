"""真实 PG 接收同键重放与冲突，读取唯一持久来源。"""

import pytest
from sqlalchemy import func, select

from test.integration.services.agent_input_fixtures import SCOPE
from test.integration.services.agent_input_fixtures import sessions as sessions
from yuxi.modules.agents.input_messages import build_chat_input_message
from yuxi.modules.agents.models.inputs import AgentInput, AgentInputReceipt
from yuxi.modules.agents.services.inputs import accept_message
from yuxi.shared.errors import StateConflictError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def test_same_key_replay_and_changed_intent_keep_one_committed_input(sessions):
    """相同意图回读同一目标，冲突不得追加或改写消息来源。"""
    async with sessions() as db:
        first = await accept_message(
            db=db,
            scope=SCOPE,
            thread_id="input-thread",
            idempotency_key="fixed-key",
            mode="follow_up",
            messages=[build_chat_input_message("original")],
        )
    async with sessions() as db:
        replay = await accept_message(
            db=db,
            scope=SCOPE,
            thread_id="input-thread",
            idempotency_key="fixed-key",
            mode="follow_up",
            messages=[build_chat_input_message("original")],
        )
        assert replay == first
        with pytest.raises(StateConflictError, match="已用于其他输入"):
            await accept_message(
                db=db,
                scope=SCOPE,
                thread_id="input-thread",
                idempotency_key="fixed-key",
                mode="follow_up",
                messages=[build_chat_input_message("changed")],
            )
        await db.rollback()
    async with sessions() as oracle:
        assert await oracle.scalar(select(func.count()).select_from(AgentInput)) == 1
        assert await oracle.scalar(select(func.count()).select_from(AgentInputReceipt)) == 1
        receipt = await oracle.scalar(select(AgentInputReceipt))
        original = await oracle.get(AgentInput, first["input_id"])
        assert receipt.input_id == original.id and receipt.id == first["event_id"]
        assert original.messages[0]["content"] == [{"type": "text", "text": "original"}]
