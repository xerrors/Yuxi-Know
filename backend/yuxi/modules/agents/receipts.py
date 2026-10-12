"""Input 与控制命令共用的幂等键、指纹及回执比较。"""

from yuxi.modules.agents.models.inputs import AgentInputReceipt
from yuxi.shared.errors import InvalidInputError, StateConflictError
from yuxi.shared.hashing import json_intent_hash


def require_idempotency_key(key: str) -> None:
    """接收边界校验客户端幂等键，保持原长度语义。"""
    if not isinstance(key, str) or not 1 <= len(key) <= 128:
        raise InvalidInputError("Idempotency-Key 长度必须为 1 至 128")


def input_intent_hash(*parts) -> str:
    """输入和交互响应保留原字符串适配及顺序指纹。"""
    return json_intent_hash(parts, default=str)


def control_intent_hash(*parts) -> str:
    """控制命令保留原严格 JSON 指纹。"""
    return json_intent_hash(parts)


def require_receipt_replay(receipt: AgentInputReceipt, event_type: str, intent_hash: str) -> None:
    """仅同一命令与同一规范意图可以重放。"""
    if receipt.event_type != event_type or receipt.intent_hash != intent_hash:
        raise StateConflictError("Idempotency-Key 已用于其他输入")
