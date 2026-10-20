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

    reason: str = Field(description="实际发生的问题或经验、相关步骤或错误、已尝试的处理与当前结果；去除首尾空白后 1 至 4000 字符")


@tool(
    category="builtin",
    display_name="记录改进线索",
    args_schema=ImprovementInput,
    description=(
        "出现以下任一情况时，主动调用此工具记录改进线索，无需用户要求："
        "用户纠正你的理解、回答、操作或结果；用户反复表达不满意或指出同一要求仍未满足；"
        "工具调用报错、超时或返回无法完成预期操作的结果；"
        "缺少完成任务所需的工具、权限、配置、依赖或其他能力。"
        "问题尚未解决、原因尚未确认时也要记录，不必等待形成成功经验。"
        "多次尝试后找到有实际依据的可复用方法或脚本时，也应记录。"
        "reason 简要说明实际发生了什么、相关步骤或错误、已尝试的处理与当前结果；"
        "有依据时说明用户期望和实际结果的差异、可复用经验或产物位置，区分事实与推测，须非空且不超过 4000 字符。"
        "同一问题或经验不重复记录，有新增事实或不同问题时再记录；普通完成任务不必记录。"
        "记录后继续处理原任务；本工具自身失败时不要循环调用，也不要声称已保存。"
        "记录只供平台后续复盘，不表示问题已解决、经验已验证或 Skill 已更新。"
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
