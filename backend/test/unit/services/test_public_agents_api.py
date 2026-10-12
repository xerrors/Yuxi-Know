"""Public Thread wire 输入与身份映射的轻量契约。"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from yuxi.api.routers.public_v1.agents.schemas import InputMessage, SessionEventCreate, input_messages_to_domain
from yuxi.api.routers.public_v1.agents.auth import require_public_context
from yuxi.modules.agents.services.inputs import _accepted, thread_id_for_creation
from yuxi.modules.agents.scope import ActorScope


def test_creation_key_is_stable_and_isolated_by_app():
    """创建幂等键稳定生成同一 Thread ID，APP 命名空间相互隔离。"""
    product = ActorScope(uid="user-1", app_id=None)
    app = ActorScope(uid="user-1", app_id="app-1")
    assert thread_id_for_creation(product, "key-1") == thread_id_for_creation(product, "key-1")
    assert thread_id_for_creation(product, "key-1") != thread_id_for_creation(app, "key-1")
    assert thread_id_for_creation(app, "key-1") != thread_id_for_creation(app, "key-2")


@pytest.mark.asyncio
async def test_unbound_full_key_uses_product_user_without_end_user():
    """CLI 浏览器登录的完整 Key 可进入产品 Thread 作用域。"""
    owner = SimpleNamespace(uid="owner-1", role="user")
    key = SimpleNamespace(id=17, access_level="full", app_id=None)
    request = SimpleNamespace(state=SimpleNamespace(api_key=key))
    context = await require_public_context(request, end_user_id=None, owner=owner, db=object())
    assert context.user is owner
    assert context.scope == ActorScope(uid="owner-1", app_id=None, api_key_id=17)

    with pytest.raises(HTTPException) as exc:
        await require_public_context(request, end_user_id="spoofed", owner=owner, db=object())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_unbound_agents_key_still_cannot_enter_public_agent_scope():
    """受限 Key 不得借无 APP 的完整 Key 路径越权。"""
    owner = SimpleNamespace(uid="owner-1", role="user")
    key = SimpleNamespace(id=18, access_level="agents", app_id=None)
    request = SimpleNamespace(state=SimpleNamespace(api_key=key))
    with pytest.raises(HTTPException) as exc:
        await require_public_context(request, end_user_id=None, owner=owner, db=object())
    assert exc.value.status_code == 403


def test_multimodal_input_keeps_part_order_and_image_media_type():
    """图文交错内容在 HTTP 规范化后保留原顺序与图片 MIME。"""
    message = InputMessage.model_validate(
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "第一张"},
                {"type": "input_image", "image_url": "data:image/png;base64,YQ=="},
                {"type": "input_text", "text": "第二张"},
                {"type": "input_image", "image_url": "data:image/webp;base64,Yg=="},
            ],
        }
    )
    built = input_messages_to_domain([message])[0]
    assert [part["type"] for part in built.langchain_message.content] == ["text", "image_url", "text", "image_url"]
    assert built.langchain_message.content[1]["image_url"]["url"] == "data:image/png;base64,YQ=="
    assert built.langchain_message.content[3]["image_url"]["url"] == "data:image/webp;base64,Yg=="


@pytest.mark.parametrize("mode", ["follow_up", "steer"])
def test_message_priority_has_no_target_turn(mode):
    """普通消息的优先级不携带执行目标，旧 Turn 字段在 wire 边界拒绝。"""
    event = {
        "type": "agent.session.input.message",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "message"}]}],
        "yuxi": {"mode": mode},
    }
    accepted = SessionEventCreate.model_validate({"events": [event]})
    assert accepted.events[0].yuxi.mode == mode
    event["yuxi"]["turn_id"] = "ended-turn"
    with pytest.raises(ValidationError, match="turn_id"):
        SessionEventCreate.model_validate({"events": [event]})


def test_receipt_returns_identity_and_consumption_without_effective_mode():
    """回执只返回持久接收及消费归属，不需要有效模式字段。"""
    receipt = SimpleNamespace(id="receipt", input_id="batch", thread_id="thread", turn_id=None, run_id=None)
    assert _accepted(receipt) == {
        "event_id": "receipt",
        "input_id": "batch",
        "thread_id": "thread",
        "turn_id": None,
        "run_id": None,
        "status": "accepted",
    }


def test_wire_rejects_unknown_fields_and_remote_images():
    """未定义命令字段与远程图片在持久化前被拒绝。"""
    with pytest.raises(ValidationError):
        SessionEventCreate.model_validate(
            {
                "events": [
                    {
                        "type": "agent.session.input.message",
                        "input": [],
                        "request_id": "old",
                        "yuxi": {"mode": "follow_up"},
                    }
                ]
            }
        )
    message = InputMessage.model_validate({"role": "user", "content": [{"type": "input_image", "image_url": "https://example.com/a.png"}]})
    with pytest.raises(HTTPException) as exc:
        input_messages_to_domain([message])
    assert exc.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("external_id", ["", " leading", "trailing ", "a" * 129])
async def test_invalid_end_user_id_maps_identity_error_to_422(external_id):
    """非法外部身份在访问数据库前返回既有 HTTP 错误。"""
    owner = SimpleNamespace(uid="owner-1", role="user")
    key = SimpleNamespace(id=19, access_level="agents", app_id="app-1")
    request = SimpleNamespace(state=SimpleNamespace(api_key=key))
    with pytest.raises(HTTPException) as exc:
        await require_public_context(request, end_user_id=external_id, owner=owner, db=object())
    assert exc.value.status_code == 422
    assert exc.value.detail == "X-End-User-Id 必须为 1 至 128 个无首尾空白的字符"
