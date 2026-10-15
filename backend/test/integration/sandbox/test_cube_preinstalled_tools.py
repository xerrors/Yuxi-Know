"""普通用户预装浏览器、CLI 与文档工具的真实产物验收。"""

import json
import struct
from zipfile import ZipFile

import pytest

from yuxi.modules.workspace.paths import user_workspace_dir

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.slow, pytest.mark.self_managed_resources]


def test_default_user_browser_document_and_python_tools(resources, tmp_path):
    """从普通账号操作网页和文件，宿主独立回读下载、图像、PDF 与工作簿。"""
    uid, _, _, backend = resources
    result = backend.execute(
        r'''python3 - <<'PY'
import json, os, subprocess, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx, openpyxl, pymysql
from bs4 import BeautifulSoup
from PIL import Image
from playwright.sync_api import sync_playwright

marker = 'YUXI_TOOLKIT_CHECK'
html = (
    '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Yuxi tools</title>'
    '<style>body{font-family:"Noto Sans CJK SC",sans-serif;padding:40px;background:#f4f7f5}'
    'h1{color:#176b47}</style><h1>中文字体与网页工具验收</h1>'
    '<p>YUXI_TOOLKIT_CHECK</p><a id="download" href="/download">下载文件</a></html>'
).encode()

class Handler(BaseHTTPRequestHandler):
    """只为验收提供本机页面和固定下载字节。"""

    def do_GET(self):
        """返回页面或附件，避免验收依赖外部网站。"""
        download = self.path == '/download'
        data = marker.encode() if download else html
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream' if download else 'text/html; charset=utf-8')
        if download:
            self.send_header('Content-Disposition', 'attachment; filename="download.txt"')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        """验收不记录请求日志。"""

def run(*args, input=None):
    """真实执行 CLI，并要求成功退出。"""
    return subprocess.check_output(args, input=input, text=True).strip()

assert os.getuid() != 0
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{server.server_port}'
try:
    response = httpx.get(url, trust_env=False)
    response.raise_for_status()
    heading = BeautifulSoup(response.text, 'html.parser').h1.get_text()
    assert run('curl', '--noproxy', '*', '-fsS', url) == response.text
    assert run('wget', '--no-proxy', '-qO-', url) == response.text
    jq_result = run('jq', '.value', input='{"value":42}')
    font = run('fc-match', '-f', '%{family}', ':lang=zh-cn')
    assert 'Noto Sans CJK' in font, font

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, chromium_sandbox=True)
        page = browser.new_page(viewport={'width': 900, 'height': 600})
        page.goto(url)
        assert page.title() == 'Yuxi tools'
        assert page.locator('h1').inner_text() == heading
        page.evaluate('document.fonts.ready')
        page.screenshot(path='browser.png')
        page.pdf(path='browser.pdf', print_background=True)
        with page.expect_download() as download:
            page.locator('#download').click()
        download.value.save_as('download.txt')
        browser_version = browser.version
        browser.close()

    pdf_info = run('pdfinfo', 'browser.pdf')
    run('pdftotext', 'browser.pdf', 'browser.txt')
    run('pdftoppm', '-f', '1', '-singlefile', '-scale-to', '800', '-png', 'browser.pdf', 'pdf-page')
    run('rg', '--fixed-strings', marker, 'browser.txt')
    pdf_mime = run('file', '-b', '--mime-type', 'browser.pdf')
    run('zip', '-q', 'download.zip', 'download.txt')
    unzipped = run('unzip', '-p', 'download.zip', 'download.txt')
    Image.new('RGB', (32, 32), '#176b47').save('python-image.png')
    workbook = openpyxl.Workbook()
    workbook.active.append([marker, 42])
    workbook.save('report.xlsx')
    Path('tools-result.json').write_text(json.dumps({
        'uid': os.getuid(), 'heading': heading, 'font': font, 'jq': jq_result,
        'browser': browser_version, 'pdf_info': pdf_info, 'pdf_mime': pdf_mime,
        'unzipped': unzipped, 'mysql_escaped': pymysql.converters.escape_string("'"),
    }), encoding='utf-8')
finally:
    server.shutdown()
    server.server_close()
PY''',
        timeout=180,
    )
    assert result.exit_code == 0, result.output
    root = user_workspace_dir(uid)
    observed = json.loads((root / "tools-result.json").read_text())
    assert observed["uid"] != 0
    assert observed["heading"] == "中文字体与网页工具验收"
    assert observed["jq"] == "42"
    assert observed["pdf_mime"] == "application/pdf"
    assert observed["unzipped"] == "YUXI_TOOLKIT_CHECK"
    assert observed["mysql_escaped"] == "\\'"
    assert (root / "download.txt").read_bytes() == b"YUXI_TOOLKIT_CHECK"
    pdf_text = (root / "browser.txt").read_text()
    assert "YUXI_TOOLKIT_CHECK" in pdf_text
    assert "中文字体与网页工具验收" in pdf_text
    with ZipFile(root / "report.xlsx") as workbook:
        sheet = workbook.read("xl/worksheets/sheet1.xml")
        assert b"YUXI_TOOLKIT_CHECK" in sheet
        assert b"<v>42</v>" in sheet
    for name in ("browser.png", "pdf-page.png", "python-image.png"):
        content = (root / name).read_bytes()
        assert content[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = struct.unpack(">II", content[16:24])
        assert width > 0 and height > 0
        if name == "browser.png":
            assert (width, height) == (900, 600)
        (tmp_path / name).write_bytes(content)
    (tmp_path / "browser.pdf").write_bytes((root / "browser.pdf").read_bytes())
