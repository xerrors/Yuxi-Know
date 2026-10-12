"""保存当前执行中值得复盘的经验候选。"""

from langchain_core.tools import ToolException
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.agents.services.feedback import mark_run_for_improvement
from yuxi.modules.extensions.tools.registry import tool
from yuxi.shared.errors import DomainError


class ImprovementInput(BaseModel):
    """模型仅提供待复盘原因，执行身份由 runtime 注入。"""

    reason: str = Field(description="发生了什么、可复用经验及步骤或产物依据；去除首尾空白后 1 至 4000 字符")


@tool(
    category="builtin",
    display_name="记录改进线索",
    args_schema=ImprovementInput,
    description=(
        "当用户明确纠正当前操作流程，或你在多次尝试后找到可复用且有实际依据的方法、脚本时，调用此工具。"
        "reason 简要说明发生了什么、值得保留的经验，以及依据所在的步骤或产物，须非空且不超过 4000 字符。"
        "同一经验记录一次；普通完成任务不必记录。记录只供平台后续复盘，不表示经验已验证或 Skill 已更新。"
        "不要包含凭据或不必要的原始用户内容。"
    ),
)
async def mark_for_improvement(reason: str, runtime: ToolRuntime) -> dict:
    """从注入的运行上下文读取身份，提交后返回记录 ID。"""
    context = runtime.context
    if not context.run_id or not runtime.tool_call_id:
        raise ToolException("未绑定真实 Run 或工具调用，无法保存改进线索。")
    try:
        async with pg_manager.get_async_session_context() as db:
            record = await mark_run_for_improvement(
                db=db,
                run_id=context.run_id,
                uid=context.uid,
                thread_id=context.thread_id,
                worker_id=context.worker_id,
                tool_call_id=runtime.tool_call_id,
                reason=reason,
            )
    except DomainError as exc:
        raise ToolException(f"改进线索未保存：{exc.message}") from exc
    except SQLAlchemyError as exc:
        raise ToolException("数据库写入失败，改进线索未确认保存；可以使用相同调用重试。") from exc
    return {"id": record["id"], "run_id": record["run_id"], "saved": True}
