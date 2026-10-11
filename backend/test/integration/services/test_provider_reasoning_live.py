"""显式启用的小量真实模型探针；每个 model spec 只进行一次工具调用和一次续答。

运行：YUXI_REASONING_PROBE_MODELS='provider:model,...' uv run pytest -s <本文件>
"""

import asyncio
import json
import os
from time import monotonic
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from yuxi.modules.models.chat import load_chat_model
from yuxi.modules.models.providers.cache import model_cache

MODEL_SPECS = [spec.strip() for spec in os.getenv("YUXI_REASONING_PROBE_MODELS", "").split(",") if spec.strip()]

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("spec", MODEL_SPECS or [None])
@pytest.mark.asyncio
async def test_live_reasoning_tool_roundtrip(spec):
    """验证真实推理流、工具参数、续答回传和最终模型正文，不输出推理原文。"""
    if spec is None:
        pytest.skip("仅在显式配置 YUXI_REASONING_PROBE_MODELS 时调用计费服务")
    info = model_cache.get_model_info(spec)
    assert info and info.api_key, "指定测试模型必须存在且配置凭据"
    requests = []
    enable_thinking = os.getenv("YUXI_REASONING_PROBE_THINKING") == "1"

    async def capture(request):
        """只在内存核对出站协议，不记录认证字段。"""
        requests.append(json.loads(request.content))

    tool = {
        "type": "function",
        "function": {
            "name": "read_test_function",
            "description": "Read the Python function to review.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
    inputs = [
        HumanMessage(
            "Review a Python function intended to double its input. First call read_test_function, "
            "then state whether the implementation is correct and give the corrected line if needed."
        )
    ]
    started = monotonic()
    async with httpx.AsyncClient(event_hooks={"request": [capture]}, timeout=120) as client:
        model = load_chat_model(spec, session_id=f"yuxi-provider-probe-{uuid4()}", http_async_client=client, max_retries=0, timeout=120)
        request_options = {}
        if enable_thinking:
            extra_body = dict(info.request_body_overrides)
            if info.provider_id.startswith("siliconflow"):
                extra_body["enable_thinking"] = True
            else:
                extra_body["thinking"] = {"type": "enabled"}
            request_options["extra_body"] = extra_body
        async with asyncio.timeout(180):
            chunks = [chunk async for chunk in model.bind_tools([tool]).astream(inputs, **request_options)]
            result = chunks[0]
            for chunk in chunks[1:]:
                result += chunk
            reasoning = "".join(b["reasoning"] for b in result.content_blocks if b["type"] == "reasoning")
            assert len(result.tool_calls) == 1
            call = result.tool_calls[0]
            assert call["name"] == "read_test_function" and call["args"] == {}
            inputs.extend([result, ToolMessage("def double(x):\n    return x + 1", tool_call_id=call["id"])])
            answer = await model.ainvoke(inputs, **request_options)
            assert answer.text.strip(), "工具续答没有正文"
            answer_reasoning = "".join(b["reasoning"] for b in answer.content_blocks if b["type"] == "reasoning")
            if reasoning:
                assert requests[-1]["messages"][-2]["reasoning_content"] == reasoning
            assert "read_test_function" in json.dumps(requests[0]["tools"])
    print(
        json.dumps(
            {
                "model": spec,
                "requests": len(requests),
                "reasoning_chars": len(reasoning),
                "answer_reasoning_chars": len(answer_reasoning),
                "explicit_thinking": enable_thinking,
                "answer_chars": len(answer.text),
                "stream_usage": result.usage_metadata,
                "answer_usage": answer.usage_metadata,
                "seconds": round(monotonic() - started, 2),
            },
            ensure_ascii=False,
        )
    )
