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
    is_approved = interrupt(interrupt_info)

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
