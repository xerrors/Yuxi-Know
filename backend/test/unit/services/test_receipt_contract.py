"""幂等共同契约保持持久指纹字节和领域冲突。"""

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from yuxi.modules.agents.receipts import control_intent_hash, input_intent_hash, require_idempotency_key, require_receipt_replay
from yuxi.shared.errors import InvalidInputError, StateConflictError
from yuxi.shared.hashing import json_intent_hash


def test_existing_receipt_hashes_keep_canonical_bytes_and_order():
    """固定规范字节独立于 helper，旧 Receipt 无需迁移。"""
    payload = {"message": "你好", "images": ["first", "second"]}
    canonical = '[{"images":["first","second"],"message":"你好"},"follow_up"]'.encode()
    expected = hashlib.sha256(canonical).hexdigest()
    assert input_intent_hash(payload, "follow_up") == expected
    assert control_intent_hash(payload, "follow_up") == expected
    assert input_intent_hash("follow_up", payload) != expected
    assert input_intent_hash({"images": ["second", "first"], "message": "你好"}, "follow_up") != expected
    object_bytes = '{"images":["first","second"],"message":"你好"}'.encode()
    assert json_intent_hash(payload) == hashlib.sha256(object_bytes).hexdigest()
    assert json_intent_hash(payload) != expected


def test_input_date_adaptation_keeps_original_string_encoding():
    """Input 历史允许字符串适配，严格控制命令不扩大输入契约。"""
    value = datetime(2026, 10, 12, tzinfo=UTC)
    canonical = b'["2026-10-12 00:00:00+00:00"]'
    assert input_intent_hash(value) == hashlib.sha256(canonical).hexdigest()
    with pytest.raises(TypeError):
        control_intent_hash(value)


@pytest.mark.parametrize("key", [None, 1, "", "x" * 129])
def test_invalid_receipt_key_rejected_at_owning_boundary(key):
    """非字符串、空值与超过既有上限的键明确拒绝。"""
    with pytest.raises(InvalidInputError):
        require_idempotency_key(key)


def test_same_command_and_intent_replay_only():
    """命令与指纹任一变化均返回协议独立的领域冲突。"""
    require_idempotency_key("x")
    require_idempotency_key("x" * 128)
    receipt = SimpleNamespace(event_type="message", intent_hash="original")
    require_receipt_replay(receipt, "message", "original")
    for command, intent in [("cancel", "original"), ("message", "different")]:
        with pytest.raises(StateConflictError, match="已用于其他输入"):
            require_receipt_replay(receipt, command, intent)
