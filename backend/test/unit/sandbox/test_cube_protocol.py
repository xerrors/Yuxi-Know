"""用固定协议帧与真实子进程验证执行协议与取消脚本。"""

import json
import os
import struct
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from yuxi.modules.agents.runtime.sandbox.cube import _CANCEL_SCRIPT, MAX_FRAME_BYTES, connect_events


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


def _run_cancel_script(env: dict) -> subprocess.CompletedProcess:
    """以独立进程执行取消脚本，避免在测试进程内发信号。"""
    return subprocess.run([sys.executable, "-c", _CANCEL_SCRIPT], env=env, capture_output=True, text=True, timeout=30)


def _tombstone(execution: str) -> Path:
    return Path("/tmp") / f".yuxi-cancel-{execution}"


def test_cancel_script_removes_tombstone_after_confirmed_group_stop():
    """恢复泄漏缺陷：已启动命令组取消确认终止后必须移除 tombstone。"""
    execution = "unit-" + uuid.uuid4().hex
    tombstone = _tombstone(execution)
    child = subprocess.Popen(["sleep", "30"], env={**os.environ, "YUXI_EXECUTION_ID": execution}, start_new_session=True)
    try:
        result = _run_cancel_script(
            {"YUXI_PGID": str(child.pid), "YUXI_EXECUTION": execution, "YUXI_TERMINAL": "0", "PATH": os.environ["PATH"]}
        )
        assert result.returncode == 0, result.stderr
        assert child.wait(timeout=5) != 0
        assert not tombstone.exists()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(5)
        tombstone.unlink(missing_ok=True)


def test_cancel_script_removes_tombstone_for_recorded_group_that_already_ended():
    """start 事件已登记 pgid 的命令结束后取消，tombstone 不再保留。"""
    execution = "unit-" + uuid.uuid4().hex
    tombstone = _tombstone(execution)
    try:
        result = _run_cancel_script({"YUXI_PGID": "999999", "YUXI_EXECUTION": execution, "YUXI_TERMINAL": "0", "PATH": os.environ["PATH"]})
        assert result.returncode == 0, result.stderr
        assert not tombstone.exists()
    finally:
        tombstone.unlink(missing_ok=True)


def test_cancel_script_removes_tombstone_on_confirmed_terminal():
    """取得真实 end 的取消保持移除 tombstone。"""
    execution = "unit-" + uuid.uuid4().hex
    tombstone = _tombstone(execution)
    try:
        result = _run_cancel_script({"YUXI_PGID": "", "YUXI_EXECUTION": execution, "YUXI_TERMINAL": "1", "PATH": os.environ["PATH"]})
        assert result.returncode == 0, result.stderr
        assert not tombstone.exists()
    finally:
        tombstone.unlink(missing_ok=True)


def test_cancel_script_keeps_tombstone_when_start_cannot_be_confirmed():
    """无法证明 wrapper 已启动时保留 tombstone 拦截可能迟到的启动。"""
    execution = "unit-" + uuid.uuid4().hex
    tombstone = _tombstone(execution)
    try:
        result = _run_cancel_script({"YUXI_PGID": "", "YUXI_EXECUTION": execution, "YUXI_TERMINAL": "0", "PATH": os.environ["PATH"]})
        assert result.returncode == 0, result.stderr
        assert tombstone.exists()
    finally:
        tombstone.unlink(missing_ok=True)
