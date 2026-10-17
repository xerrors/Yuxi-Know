"""观测地址的内部调用仍执行平台身份约束。"""

import pytest

from yuxi.modules.agents.repositories.feedback import AgentFeedbackRepository
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.services.trace_links import get_feedback_turn_trace, get_thread_turn_trace
from yuxi.shared.errors import PermissionDeniedError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope",
    [
        ActorScope(uid="user", app_id=None),
        ActorScope(uid="admin", app_id=None, is_superadmin=True, api_key_id=1),
        ActorScope(uid="admin", app_id="app", is_superadmin=True),
    ],
)
async def test_alternative_trace_read_paths_reject_nonplatform_identity(scope):
    """绕过 HTTP 依赖的调用也必须在数据库访问前拒绝。"""
    with pytest.raises(PermissionDeniedError):
        await get_thread_turn_trace(db=object(), scope=scope, thread_id="thread", turn_id="turn")
    with pytest.raises(PermissionDeniedError):
        await get_feedback_turn_trace(db=object(), scope=scope, feedback_id="feedback")
    with pytest.raises(PermissionDeniedError):
        await AgentFeedbackRepository(object()).get_platform_turn(feedback_id="feedback", scope=scope)
