"""从工具原始结果派生审计文本、公开内容和失败语义。"""

import json
from dataclasses import dataclass
from typing import Any

TOOL_FAILURE_MESSAGE = "工具执行失败"


@dataclass(frozen=True, slots=True)
class ToolResult:
    """两种读模型共享执行结局，公开内容遵循 input content 协议。"""

    audit_content: str
    public_content: Any
    error: str | None


def tool_result_text(value: Any) -> str:
    """工具执行审计与 checkpoint 对账共用稳定 JSON 文本规则。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def normalize_tool_result(output: Any, *, message: str | None = None) -> ToolResult:
    """保留合法结构化内容，只在这里确定文本和失败原因。"""
    value = output.get("content") if isinstance(output, dict) else output
    text = tool_result_text(value)
    public = value
    if isinstance(value, list):
        if all(isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str) for part in value):
            public = [{"type": "input_text", "text": part["text"]} for part in value]
        elif not all(isinstance(part, dict) and part.get("type") in {"input_text", "input_image"} for part in value):
            public = text
    elif value is not None and not isinstance(value, str):
        public = text
    failed = isinstance(output, dict) and output.get("status") == "error"
    return ToolResult(audit_content=text, public_content=public, error=str(message or text or TOOL_FAILURE_MESSAGE) if failed else None)
