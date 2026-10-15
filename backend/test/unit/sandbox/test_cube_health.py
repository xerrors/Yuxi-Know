"""真实 HTTP 响应证明控制面在线不能掩盖代理启动失败。"""

import json
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cubesandbox import Config
import pytest

from yuxi.modules.agents.runtime.sandbox.cube import CubeAdapter


@contextmanager
def http_server(routes):
    """运行本机 HTTP 服务，None 响应用于复现代理空断连。"""

    class Handler(BaseHTTPRequestHandler):
        """只处理测试中固定的服务契约。"""

        def do_GET(self):
            """返回 HTTP 结果或主动关闭尚未响应的连接。"""
            result = routes.get(self.path, (404, {}))
            if result is None:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.close_connection = True
                return
            status, payload = result
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            """测试不写 HTTP 访问日志。"""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def adapter(api_port, proxy_port):
    """把适配器连接到本机独立的控制面和代理。"""
    return CubeAdapter(
        Config(
            api_url=f"http://127.0.0.1:{api_port}",
            proxy_node_ip="127.0.0.1",
            proxy_port=proxy_port,
            template_id="fixture-template",
        )
    )


CONTROL_ROUTES = {
    "/health": (200, {"status": "ok", "sandboxes": 0}),
    "/templates/aliases/fixture-template": (200, {"templateID": "fixture-template"}),
}


def test_readiness_accepts_live_control_plane_and_proxy(tmp_path):
    """API、模板与代理都能响应时页面允许创建环境。"""
    with http_server(CONTROL_ROUTES) as api_port, http_server({"/": (400, {"error": "bad request"})}) as proxy_port:
        assert adapter(api_port, proxy_port).health()["status"] == "ok"


def test_readiness_rejects_proxy_empty_disconnect_even_with_healthy_api(tmp_path):
    """代理复现空断连时不能继续向用户宣称 Cube 已就绪。"""
    with http_server(CONTROL_ROUTES) as api_port, http_server({"/": None}) as proxy_port:
        with pytest.raises(RuntimeError, match="CubeProxy"):
            adapter(api_port, proxy_port).health()
