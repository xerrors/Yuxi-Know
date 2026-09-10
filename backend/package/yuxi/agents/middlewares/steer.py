"""主会话 Steer / Guided Middleware。"""

from langchain.agents.middleware import AgentMiddleware, hook_config


class SteerMiddleware(AgentMiddleware):
    """在模型调用前的安全边界处理队列干预。

    - guided：把等待注入的补充消息追加进当前 Run 的 messages，模型下一轮即看到，
      当前 Run 不终止（Claude Code 式中途修正）。
    - steer：结束当前 Run，让位给高优先级 Steer 请求。
    """

    @hook_config(can_jump_to=["end"])
    async def abefore_model(self, state, runtime):  # noqa: ARG002
        guided_update = await self._collect_guided_update(runtime)
        steer_jump = await self._jump_if_steer_requested(runtime)
        if steer_jump is not None:
            # 让位时 guided 消息已标记注入并随 checkpoint 留给下一个 Run。
            return steer_jump
        return guided_update

    @hook_config(can_jump_to=["end"])
    async def aafter_model(self, state, runtime):
        """兜底处理无工具模型轮次，避免 Steer 落在最后一次检查之后。"""
        if _last_message_has_tool_calls(state):
            return None
        return await self._jump_if_steer_requested(runtime)

    async def _collect_guided_update(self, runtime):
        from yuxi.services.agent_request_queue_service import take_pending_guided_messages

        run_id = getattr(runtime.context, "run_id", None)
        if not run_id:
            return None
        try:
            messages = await take_pending_guided_messages(run_id)
        except Exception:  # noqa: BLE001
            return None
        if not messages:
            return None
        return {"messages": messages}

    async def _jump_if_steer_requested(self, runtime):
        from yuxi.services.agent_request_queue_service import should_end_run_for_steer

        run_id = getattr(runtime.context, "run_id", None)
        if not run_id or not await should_end_run_for_steer(run_id):
            return None
        return {"jump_to": "end"}


def _last_message_has_tool_calls(state) -> bool:
    """判断模型最后一条消息是否仍需执行工具，避免跳过工具批次。"""
    messages = state.get("messages") if isinstance(state, dict) else None
    if not messages:
        return False
    last_message = messages[-1]
    if isinstance(last_message, dict):
        return bool(last_message.get("tool_calls"))
    return bool(getattr(last_message, "tool_calls", None))
