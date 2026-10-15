"""用固定协议帧验证断流与大小限制。"""

import json
import struct

import pytest

from yuxi.modules.agents.runtime.sandbox.cube import MAX_FRAME_BYTES, connect_events


def frame(payload, flags=0):
    """构造显式审阅的测试协议帧。"""
    body = json.dumps(payload).encode()
    return bytes([flags]) + struct.pack(">I", len(body)) + body


def test_connect_frames_can_span_network_chunks():
    """网络分块不会丢失启动与终态事件。"""
    data = frame({"event": {"start": {"pid": 12}}}) + frame({"event": {"end": {"exitCode": 0}}})
    chunks = [data[:2], data[2:9], data[9:]]
    assert list(connect_events(iter(chunks))) == [{"start": {"pid": 12}}, {"end": {"exitCode": 0}}]


@pytest.mark.parametrize(
    "status,exit_code",
    [("exit status 0", 0), ("exit status 7", 7), ("signal: terminated", 143), ("signal: killed", 137)],
)
def test_connect_end_event_uses_cube_status_text(status, exit_code):
    """Cube 0.7.3 的终态文字转为 工具使用的 POSIX 退出码。"""
    data = frame({"event": {"end": {"exited": True, "status": status}}})
    assert list(connect_events(iter([data]))) == [{"end": {"exited": True, "status": status, "exitCode": exit_code}}]


@pytest.mark.parametrize(
    "data,reason",
    [
        (b"\0" + struct.pack(">I", MAX_FRAME_BYTES + 1), "超过预算"),
        (frame({"event": {}}, 1), "压缩"),
        (frame({"error": {"code": "internal"}}, 2), "协议错误"),
        (frame({"event": {}})[:-1], "不完整"),
    ],
)
def test_connect_rejects_invalid_stream(data, reason):
    """协议缺陷不会被当成有效空输出。"""
    with pytest.raises(RuntimeError, match=reason):
        list(connect_events(iter([data])))
