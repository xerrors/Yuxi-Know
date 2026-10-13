"""用真实 Nginx 验证OIDC回调成功页与上游故障的日志和响应头。"""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    """隔离容器和假回调参数，回读实际代理日志后清理。"""
    root = Path(__file__).resolve().parent.parent
    name = "oidc-proxy-probe-" + uuid4().hex[:12]
    marker = "fixture-secret-marker-" + uuid4().hex
    with tempfile.TemporaryDirectory(prefix="oidc-proxy-") as directory:
        html = Path(directory) / "index.html"
        html.write_text("<html><body>Fixture SPA callback</body></html>\n")
        try:
            subprocess.run([
                "docker", "run", "--rm", "-d", "--name", name,
                "--add-host", "api:127.0.0.1", "--add-host", "minio:127.0.0.1",
                "-p", "127.0.0.1::80",
                "-v", f"{root / 'docker/nginx/nginx.conf'}:/etc/nginx/nginx.conf:ro",
                "-v", f"{root / 'docker/nginx/default.conf'}:/etc/nginx/conf.d/default.conf:ro",
                "-v", f"{html}:/usr/share/nginx/html/index.html:ro", "nginx:alpine",
            ], check=True, capture_output=True, text=True)
            ports = json.loads(subprocess.check_output(["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", name]))
            origin = "http://127.0.0.1:" + ports["80/tcp"][0]["HostPort"]
            for path, expected in (
                ("/auth/oidc/callback", 200), ("/api/auth/oidc/callback", 502),
                ("/auth/oidc/%63allback", 200), ("//auth/oidc/callback", 200),
                ("/auth/oidc/callback/", 200), ("/%61uth/oidc/callback", 200),
                ("/api/auth/oidc/%63allback", 502), ("//api/auth/oidc/callback", 502),
                ("/api/auth/oidc/callback/", 502),
            ):
                request = Request(origin + path + "?code=" + marker + "&state=" + marker,
                                  headers={"Referer": origin + "/auth/oidc/callback?code=" + marker})
                for attempt in range(50):
                    try:
                        response = urlopen(request, timeout=2)
                        break
                    except HTTPError as exc:
                        response = exc
                        break
                    except (URLError, OSError):
                        if attempt == 49:
                            raise
                        time.sleep(0.1)
                with response:
                    assert response.code == expected, response.code
                    assert response.headers["Referrer-Policy"] == "no-referrer"
                    assert response.headers["Cache-Control"] == "no-store"
                    if expected == 200:
                        assert b"Fixture SPA callback" in response.read()
            logs = subprocess.check_output(["docker", "logs", name], stderr=subprocess.STDOUT, text=True)
            assert marker not in logs, "回调参数进入 Nginx 日志"
            assert 'GET /auth/oidc/callback HTTP/1.1" 200' in logs
            assert 'GET /api/auth/oidc/callback HTTP/1.1" 502' in logs
            print("Passed: actual Nginx callback DOM response, no-store/no-referrer, success/failure query and referer redaction")
        except Exception:
            print(subprocess.run(["docker", "logs", name], capture_output=True, text=True).stderr)
            raise
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)


if __name__ == "__main__":
    main()
