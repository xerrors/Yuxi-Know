"""测试进程异常也不会遗留队列消费者或 HTTP server。"""

import socket
import subprocess
import sys
from contextlib import contextmanager

import pytest
from test.e2e.test_cube_agent_execution_e2e import execution_resources


def test_reconciliation_error_still_stops_test_worker_and_server(tmp_path):
    """恢复原缺陷时进程与 TCP 端口仍存活，独立 oracle 会拒绝。"""
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    owner = tmp_path / "owner"
    owner.write_text("test-worker")
    server = None
    try:
        with pytest.raises(RuntimeError, match="reconcile failed"):
            with contextmanager(execution_resources.__wrapped__)() as (server, workers):
                workers.append((process, owner))
                raise RuntimeError("reconcile failed")
        assert process.poll() is not None
        assert not owner.exists()
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", server.server_port), timeout=0.2)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(5)
        if server:
            server.shutdown()
            server.server_close()
