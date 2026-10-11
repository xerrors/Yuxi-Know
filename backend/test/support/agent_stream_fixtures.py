"""Agent 流测试复用的协议事件和模型。"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def native(seq, data, method="messages"):
    """构造带稳定来源身份的原生流事件。"""
    return {
        "seq": seq,
        "method": method,
        "params": {
            "timestamp": 1777000123456,
            "namespace": ["model:x"],
            "data": (data, {"run_id": "model"}) if method == "messages" else data,
        },
    }


class FinalAnswerModel(BaseChatModel):
    """只返回最终文本，模拟 Steer 到达最后一次模型检查后的窗口。"""

    call_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "steer-final-answer"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        self.call_count += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="旧 Run 已完成当前回答"))])
