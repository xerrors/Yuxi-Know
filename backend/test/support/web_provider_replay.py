"""测试拓扑中的 HTTPS 供应商协议与 OpenAI 工具调用重放。"""

import argparse
import json
import re
import ssl
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from test.support.openai_replay_server import send_json_response, send_openai_sse_response

HOSTS = {"api.tavily.com", "api.deepseek.com", "open.feedcoopapi.com"}
PAGE_URL = "https://example.com/web-tools-replay"


def create_test_certificate(directory: Path) -> ssl.SSLContext:
    """生成仅供隔离重放拓扑信任的临时证书，不提交私钥。"""
    directory.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Yuxi test replay")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host) for host in sorted(HOSTS)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / "ca.pem", directory / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    # 重放进程以 root 生成证书，API/worker 的普通用户需要读取公共 CA。
    cert_path.chmod(0o644)
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key_path.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return context


class WebReplayHandler(BaseHTTPRequestHandler):
    """限定三家官方域名，仅返回固定 oracle，不访问互联网。"""

    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        """不记录请求体或测试凭据。"""

    def do_GET(self):
        """供 Compose 检查重放与证书是否就绪。"""
        send_json_response(self, 200, {"ready": True})

    def do_CONNECT(self):
        """在测试 CA 上终止固定供应商域名的 HTTPS 连接。"""
        if self.path not in {f"{host}:443" for host in HOSTS}:
            self.send_error(403)
            return
        self.send_response(200, "Connection established")
        self.end_headers()
        self.wfile.flush()
        self.connection = self.server.tls_context.wrap_socket(self.connection, server_side=True)
        self.rfile = self.connection.makefile("rb")
        self.wfile = self.connection.makefile("wb")
        self.handle_one_request()
        self.close_connection = True

    def do_POST(self):
        """重放搜索、正文接口与串行调用两工具的模型响应。"""
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if self.path == "/v1/chat/completions":
            return self._model_response(request)
        host = self.headers.get("Host")
        provider = {"api.tavily.com": "tavily", "api.deepseek.com": "deepseek", "open.feedcoopapi.com": "doubao"}.get(host)
        if not provider or self.headers.get("Authorization") != f"Bearer replay-{provider}-key":
            return send_json_response(self, 401, {"error": "invalid replay credentials"})
        paths = {
            "tavily": ("/search", "/extract"),
            "deepseek": ("/v1/tools/search", "/v1/tools/fetch"),
            "doubao": ("/search_api/web_search", None),
        }
        title, body = "Replay article", "# REPLAY_FETCH_BODY"
        if self.path == paths[provider][1]:
            urls = request.get("urls") if provider == "tavily" else [request.get("url")]
            if urls != [PAGE_URL]:
                return send_json_response(self, 400, {"error": "invalid fetch input"})
            payload = {"title": title, "content": body}
            if provider == "tavily":
                payload = {"results": [{"url": PAGE_URL, "raw_content": body}]}
        elif self.path == paths[provider][0]:
            query = request.get("Query" if provider == "doubao" else "query")
            count = request.get("Count" if provider == "doubao" else "max_results" if provider == "tavily" else "count")
            if (
                not isinstance(query, str)
                or not query.strip()
                or type(count) is not int
                or not 1 <= count <= (20 if provider == "tavily" else 50)
            ):
                return send_json_response(self, 400, {"error": "invalid search input"})
            item = {
                "title": title,
                "url": PAGE_URL,
                "snippet": "Short",
                "summary": "REPLAY_RELEVANT",
                "content": "REPLAY_RELEVANT",
                "score": 0.8,
                "rerank_score": 2.4,
            }
            payload = {"results": [item]}
            if provider == "doubao":
                payload = {
                    "Result": {
                        "WebResults": [
                            {
                                "Title": title,
                                "Url": PAGE_URL,
                                "Snippet": "Short",
                                "Summary": "REPLAY_RELEVANT",
                                "Content": body,
                                "RankScore": 0.8,
                            }
                        ]
                    }
                }
        else:
            return send_json_response(self, 404, {})
        send_json_response(self, 200, payload)

    def _model_response(self, request: dict):
        """要求真实工具结果满足供应商和正文语义后才输出完成标记。"""
        messages = request.get("messages", [])
        last_user = max((index for index, message in enumerate(messages) if message.get("role") == "user"), default=0)
        current = messages[last_user:]
        prompt = json.dumps(current[0].get("content", ""))
        expected = re.search(r"EXPECT_SEARCH:(tavily|deepseek|doubao) EXPECT_FETCH:(tavily|deepseek)", prompt)
        tool_names = {item.get("function", {}).get("name") for item in request.get("tools", [])}
        if not expected or not {"web_search", "web_fetch"} <= tool_names:
            return send_json_response(self, 400, {"error": "web tools or scenario missing"})
        results = [message for message in current if message.get("role") == "tool"]
        if len(results) < 2:
            name = "web_search" if not results else "web_fetch"
            args = {"query": "web tools replay", "count": 2} if not results else {"url": PAGE_URL}
            delta = {
                "role": "assistant",
                "tool_calls": [
                    {"index": 0, "id": f"call-{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
                ],
            }
            reason = "tool_calls"
        else:
            search, fetched = (json.loads(message["content"]) for message in results[-2:])
            if (
                search.get("provider") != expected[1]
                or fetched.get("provider") != expected[2]
                or fetched.get("content") != "# REPLAY_FETCH_BODY"
            ):
                return send_json_response(self, 400, {"error": "tool result mismatch"})
            delta = {"role": "assistant", "content": "WEB_TOOLS_E2E_OK"}
            reason = "stop"
        send_openai_sse_response(
            self,
            [
                {
                    "id": "web-replay",
                    "object": "chat.completion.chunk",
                    "model": "deterministic-chat",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                },
                {
                    "id": "web-replay",
                    "object": "chat.completion.chunk",
                    "model": "deterministic-chat",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
                },
            ],
        )
        self.close_connection = True


def main():
    """启动独立的测试协议服务。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--cert-dir", type=Path, default=Path("/replay-certs"))
    args = parser.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), WebReplayHandler)
    server.tls_context = create_test_certificate(args.cert_dir)
    server.serve_forever()


if __name__ == "__main__":
    main()
