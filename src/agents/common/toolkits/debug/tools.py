from langgraph.types import interrupt

from src.agents.common.toolkits.registry import tool


@tool(category="debug", tags=["内置", "审批"], display_name="人工审批")
def get_approved_user_goal(
    operation_description: str,
) -> dict:
    """
    请求人工审批，在执行重要操作前获得人类确认。

    Args:
        operation_description: 需要审批的操作描述，例如 "调用知识库工具"
    Returns:
        dict: 包含审批结果的字典，格式为 {"approved": bool, "message": str}
    """
    # 构建详细的中断信息
    interrupt_info = {
        "question": "是否批准以下操作？",
        "operation": operation_description,
    }

    # 触发人工审批
    interrupt_result = interrupt(interrupt_info)

    if isinstance(interrupt_result, bool):
        is_approved = interrupt_result
    elif isinstance(interrupt_result, str):
        is_approved = interrupt_result.strip().lower() in {"approve", "approved", "true", "yes", "1"}
    elif isinstance(interrupt_result, list):
        lowered = {str(item).strip().lower() for item in interrupt_result}
        is_approved = "approve" in lowered or "approved" in lowered
    elif isinstance(interrupt_result, dict):
        selected = interrupt_result.get("selected")
        if isinstance(selected, list):
            lowered = {str(item).strip().lower() for item in selected}
            is_approved = "approve" in lowered or "approved" in lowered
        else:
            text = str(interrupt_result.get("text") or "").strip().lower()
            is_approved = text in {"approve", "approved", "true", "yes", "1"}
    else:
        is_approved = bool(interrupt_result)

    # 返回审批结果
    if is_approved:
        result = {
            "approved": True,
            "message": f"✅ 操作已批准：{operation_description}",
        }
        print(f"✅ 人工审批通过: {operation_description}")
    else:
        result = {
            "approved": False,
            "message": f"❌ 操作被拒绝：{operation_description}",
        }
        print(f"❌ 人工审批被拒绝: {operation_description}")

    return result
