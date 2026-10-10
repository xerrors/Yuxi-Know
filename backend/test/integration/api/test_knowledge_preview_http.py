"""在隔离 PostgreSQL、Redis、MinIO 与真实 worker 验证提前预览。"""

import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import psycopg
import pytest
from minio import Minio
from openpyxl import Workbook
from pypdf import PdfReader
from redis import Redis
from sqlalchemy.engine import make_url
from yuxi.utils.auth_utils import SECURITY_SECRET_NAMES

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def wait_until(read, accept, *, seconds=90):
    """等待外部事实达到预期，超时保留最后一次读回值。"""
    deadline = time.monotonic() + seconds
    value = None
    while time.monotonic() < deadline:
        value = read()
        if accept(value):
            return value
        time.sleep(0.1)
    pytest.fail(f"外部事实未收敛: {value}")


@pytest.fixture(scope="module")
def preview_server(tmp_path_factory):
    """独立数据库和进程保留真实认证、任务发布、claim 与转换边界。"""
    isolated_redis_url = os.environ.get("PREVIEW_TEST_REDIS_URL")
    if not isolated_redis_url:
        pytest.skip("需要 PREVIEW_TEST_REDIS_URL 指向独立验收 Redis，不能复用开发队列")
    with Redis.from_url(isolated_redis_url) as redis:
        if next(redis.scan_iter(match="yuxi:worker:health:*"), None) is not None:
            pytest.fail("验收 Redis 上已有 worker，拒绝跨数据库消费任务")
    configured_url = os.environ.get("POSTGRES_URL")
    if not configured_url:
        pytest.fail("POSTGRES_URL 未配置真实 PostgreSQL 测试入口")
    temporary = tmp_path_factory.mktemp("knowledge-preview-http")
    database = "preview_test_" + uuid.uuid4().hex
    base = make_url(configured_url)
    admin_url = base.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    url = base.set(database=database)
    sync_url = url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{database}"')

    env = dict(
        os.environ,
        POSTGRES_URL=url.render_as_string(hide_password=False),
        REDIS_URL=isolated_redis_url,
        YUXI_SKILL_DATA_DIR=str(temporary / "skill-sources"),
    )
    env.update({name: uuid.uuid4().hex + uuid.uuid4().hex for name in SECURITY_SECRET_NAMES})
    processes = []
    logs = []
    client = None
    minio_client = None
    kb_id = "kb_preview_" + uuid.uuid4().hex[:16]
    private_kb = kb_id + "_private"

    seed = """
import asyncio
from loguru import logger
logger.remove()
from yuxi.storage.postgres.manager import pg_manager, BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION
from yuxi.storage.postgres.models_business import User, Department
from yuxi.storage.postgres.models_knowledge import KnowledgeBase
from yuxi.utils.auth_utils import AuthUtils
async def seed():
    pg_manager.initialize()
    await pg_manager.create_business_tables()
    await pg_manager.create_knowledge_tables()
    await pg_manager.create_schema_version_table()
    await pg_manager.record_schema_version('business', BUSINESS_SCHEMA_VERSION)
    await pg_manager.record_schema_version('knowledge', KNOWLEDGE_SCHEMA_VERSION)
    async with pg_manager.get_async_session_context() as session:
        department = Department(name='预览测试部门')
        session.add(department)
        await session.flush()
        for uid, role in [('preview_admin', 'superadmin'), ('preview_reader', 'user')]:
            session.add(User(uid=uid, username=uid, role=role, department_id=department.id,
                password_hash=AuthUtils.hash_password('Synthetic-preview-pass!')))
        session.add(KnowledgeBase(kb_id=KB_ID, name='预览测试库', kb_type='milvus', created_by='preview_admin',
            share_config={'version': 2, 'read_scope': {'access_level': 'global'}, 'manage_scope': None}))
        session.add(KnowledgeBase(kb_id=PRIVATE_KB, name='预览私有库', kb_type='milvus', created_by='preview_admin',
            share_config={'version': 2, 'read_scope': None, 'manage_scope': None}))
    await pg_manager.close()
asyncio.run(seed())
"""
    seed = f"KB_ID={kb_id!r}\nPRIVATE_KB={private_kb!r}\n" + seed

    def start_process(command, name):
        """使用私有日志启动验收进程，关闭时回收。"""
        log = (temporary / (name + ".log")).open("w")
        logs.append(log)
        process = subprocess.Popen(command, env=env, cwd=temporary, stdout=log, stderr=log)
        processes.append(process)
        return process

    try:
        seeded = subprocess.run([sys.executable, "-c", seed], env=env, cwd=temporary, capture_output=True, text=True)
        assert seeded.returncode == 0, seeded.stderr[-4000:]
        app_file = temporary / "preview_http_app.py"
        app_file.write_text(
            "from loguru import logger\nlogger.remove()\n"
            "from fastapi import FastAPI\n"
            "from server.routers.auth_router import auth\n"
            "from server.routers.knowledge_router import knowledge\n"
            "from server.routers.workspace_router import workspace, workspace_knowledge\n"
            "from server.utils.access_log_middleware import AccessLogMiddleware\n"
            "from yuxi.storage.postgres.manager import pg_manager\n"
            "pg_manager.initialize()\napp = FastAPI()\n"
            "app.add_middleware(AccessLogMiddleware)\n"
            "app.include_router(auth, prefix='/api')\n"
            "app.include_router(knowledge, prefix='/api')\n"
            "app.include_router(workspace, prefix='/api')\n"
            "app.include_router(workspace_knowledge, prefix='/api')\n",
            encoding="utf-8",
        )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        api = start_process(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "preview_http_app:app",
                "--app-dir",
                str(temporary),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            "api",
        )
        endpoint = f"http://127.0.0.1:{port}"
        client = httpx.Client(base_url=endpoint, timeout=30, trust_env=False)

        def live():
            """API 必须真的接受 HTTP 请求。"""
            if api.poll() is not None:
                pytest.fail((temporary / "api.log").read_text()[-4000:])
            try:
                return client.get("/api/auth/check-first-run").status_code
            except httpx.ConnectError:
                return None

        wait_until(live, lambda status: status == 200)
        headers = {}
        for role, uid in [("admin", "preview_admin"), ("reader", "preview_reader")]:
            login = client.post("/api/auth/token", data={"username": uid, "password": "Synthetic-preview-pass!"})
            assert login.status_code == 200, login.text
            headers[role] = {"Authorization": "Bearer " + login.json()["access_token"]}
        minio_client = Minio(
            os.environ["MINIO_URI"].split("://", 1)[-1],
            access_key=os.environ["MINIO_ACCESS_KEY"],
            secret_key=os.environ["MINIO_SECRET_KEY"],
            secure=False,
        )
        yield SimpleNamespace(
            temporary=temporary,
            client=client,
            url=sync_url,
            kb_id=kb_id,
            private_kb=private_kb,
            headers=headers,
            start_worker=lambda: start_process([sys.executable, "-m", "server.worker_main"], "worker"),
            minio=minio_client,
        )
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        for log in logs:
            log.close()
        if client is not None:
            client.close()
        try:
            if minio_client is not None and minio_client.bucket_exists("knowledgebases"):
                for item in minio_client.list_objects("knowledgebases", prefix=kb_id + "/", recursive=True):
                    minio_client.remove_object("knowledgebases", item.object_name)
        finally:
            with psycopg.connect(admin_url, autocommit=True) as connection:
                connection.execute(f'DROP DATABASE "{database}" WITH (FORCE)')


def task_rows(server, file_id):
    """从 PostgreSQL 读取对应文件的真实 Task 终态。"""
    with psycopg.connect(server.url) as connection:
        return connection.execute(
            "SELECT id, status, result, error FROM tasks "
            "WHERE type='knowledge_preview' AND payload->>'file_id'=%s ORDER BY created_at",
            (file_id,),
        ).fetchall()


def upload_and_add(server, filename, content):
    """执行产品实际上传和只添加入口。"""
    uploaded = server.client.post(
        "/api/knowledge/files/upload",
        params={"kb_id": server.kb_id},
        files={"file": (filename, content)},
        headers=server.headers["admin"],
    )
    assert uploaded.status_code == 200, (uploaded.text, (server.temporary / "api.log").read_text()[-3500:])
    original = uploaded.json()
    path = original["file_path"]
    added = server.client.post(
        f"/api/knowledge/databases/{server.kb_id}/documents/add",
        json={
            "items": [path],
            "params": {"content_hashes": {path: original["content_hash"]}, "file_sizes": {path: len(content)}},
        },
        headers=server.headers["admin"],
    )
    assert added.status_code == 200 and added.json()["added"] == 1, added.text
    return added.json()["items"][0]["file_id"], original


def object_bytes(server, key):
    """回读真实 MinIO 字节并关闭连接。"""
    response = server.minio.get_object("knowledgebases", key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def test_uploaded_office_prepares_cache_before_preview_and_reuses_it(preview_server):
    """先回读 worker 产物再点预览，原件、权限、去重与失败均由外部事实证明。"""
    server = preview_server
    workbook = Workbook()
    workbook.active["A1"] = "preview-cache-marker"
    for row in range(2, 180):
        workbook.active.append([row, row * 3, row * 7])
    output = io.BytesIO()
    workbook.save(output)
    original = output.getvalue()
    file_id, uploaded = upload_and_add(server, "preview.xlsx", original)
    rows = task_rows(server, file_id)
    assert len(rows) == 1 and rows[0][1] == "pending"
    preview_params = {"kb_id": server.kb_id, "file_id": file_id}
    reader = server.headers["reader"]
    # 存量文件没有提前任务时，并发读取在真实唯一索引上收敛。
    legacy_id = "file_preview_legacy"
    with psycopg.connect(server.url) as connection:
        connection.execute(
            "INSERT INTO knowledge_files (file_id, kb_id, filename, minio_url, path, file_size, status) "
            "SELECT %s, kb_id, filename, minio_url, path, file_size, status FROM knowledge_files WHERE file_id=%s",
            (legacy_id, file_id),
        )
    legacy_params = {**preview_params, "file_id": legacy_id}
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(
                lambda _: server.client.get("/api/workspace/knowledge/file", params=legacy_params, headers=reader),
                range(8),
            )
        )
    assert all(response.status_code == 200 and response.json().get("status") == "loading" for response in responses), [
        (response.status_code, response.text[:500]) for response in responses
    ]
    assert len(task_rows(server, legacy_id)) == 1
    assert task_rows(server, file_id) == rows

    cache_key = f"{server.kb_id}/preview/{file_id}.pdf"
    assert not list(server.minio.list_objects("knowledgebases", prefix=cache_key))
    worker = server.start_worker()

    def worker_facts():
        """启动失败立即保留原因，不能把未运行 worker 当成慢转换。"""
        if worker.poll() is not None:
            pytest.fail((server.temporary / "worker.log").read_text()[-4500:])
        return task_rows(server, file_id)

    finished = wait_until(worker_facts, lambda records: records and records[0][1] in {"success", "failed"})
    assert finished[0][1] == "success", finished
    pdf = object_bytes(server, cache_key)
    assert pdf.startswith(b"%PDF-")
    assert "preview-cache-marker" in "".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    original_hash = hashlib.sha256(original).hexdigest()
    assert hashlib.sha256(object_bytes(server, uploaded["object_name"])).hexdigest() == original_hash
    before = server.minio.stat_object("knowledgebases", cache_key)
    measurements = []
    for _ in range(2):
        started = time.monotonic()
        response = server.client.get("/api/workspace/knowledge/file", params=preview_params, headers=reader)
        measurements.append(round(time.monotonic() - started, 4))
        assert response.status_code == 200 and response.content == pdf
        assert int(response.headers["content-length"]) == len(pdf)
        assert response.headers["content-type"] == "application/pdf"
    after = server.minio.stat_object("knowledgebases", cache_key)
    assert (before.etag, before.last_modified) == (after.etag, after.last_modified)
    assert len(task_rows(server, file_id)) == 1
    print(json.dumps({"cached_http_seconds": measurements, "pdf_bytes": len(pdf)}, ensure_ascii=False))

    # 生成真正的旧版 XLS，再经产品上传和 worker 回读，避免只改变文件后缀。
    legacy_directory = server.temporary / "legacy-xls"
    legacy_directory.mkdir()
    source = legacy_directory / "legacy.xlsx"
    source.write_bytes(original)
    converted = subprocess.run(
        [
            "libreoffice",
            "-env:UserInstallation=" + (legacy_directory / "profile").as_uri(),
            "--headless",
            "--convert-to",
            "xls",
            "--outdir",
            str(legacy_directory),
            str(source),
        ],
        capture_output=True,
        timeout=60,
    )
    legacy_file = legacy_directory / "legacy.xls"
    assert converted.returncode == 0 and legacy_file.is_file(), converted.stderr
    legacy_original = legacy_file.read_bytes()
    assert legacy_original.startswith(bytes.fromhex("d0cf11e0a1b11ae1"))
    xls_id, xls_uploaded = upload_and_add(server, "legacy.xls", legacy_original)
    xls_tasks = wait_until(
        lambda: task_rows(server, xls_id), lambda records: records and records[0][1] in {"success", "failed"}
    )
    assert len(xls_tasks) == 1 and xls_tasks[0][1] == "success", xls_tasks
    xls_pdf = object_bytes(server, f"{server.kb_id}/preview/{xls_id}.pdf")
    assert "preview-cache-marker" in "".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(xls_pdf)).pages)
    assert (
        hashlib.sha256(object_bytes(server, xls_uploaded["object_name"])).digest()
        == hashlib.sha256(legacy_original).digest()
    )
    xls_response = server.client.get(
        "/api/workspace/knowledge/file", params={"kb_id": server.kb_id, "file_id": xls_id}, headers=reader
    )
    assert xls_response.status_code == 200 and xls_response.content == xls_pdf
    assert int(xls_response.headers["content-length"]) == len(xls_pdf)
    print(json.dumps({"xls_prepared_before_click": True, "xls_pdf_bytes": len(xls_pdf)}))

    count = len(task_rows(server, file_id))
    assert server.client.get("/api/workspace/knowledge/file", params=preview_params).status_code == 401
    assert (
        server.client.get(
            "/api/workspace/knowledge/file", params={**preview_params, "kb_id": server.private_kb}, headers=reader
        ).status_code
        == 403
    )
    assert (
        server.client.get(
            "/api/workspace/knowledge/file", params={**preview_params, "file_id": "missing_file"}, headers=reader
        ).status_code
        == 400
    )
    assert len(task_rows(server, file_id)) == count

    broken_id, broken = upload_and_add(server, "broken.xlsx", b"PK\x03\x04broken workbook")
    failed = wait_until(lambda: task_rows(server, broken_id), lambda records: records and records[0][1] == "failed")
    assert len(failed) == 1
    response = server.client.get(
        "/api/workspace/knowledge/file", params={"kb_id": server.kb_id, "file_id": broken_id}, headers=reader
    )
    assert response.status_code == 200 and response.json()["status"] == "error"
    assert object_bytes(server, broken["object_name"]) == b"PK\x03\x04broken workbook"
    assert not list(server.minio.list_objects("knowledgebases", prefix=f"{server.kb_id}/preview/{broken_id}.pdf"))

    workbook.active["B1"] = "independent-submission-failure"
    recovered_output = io.BytesIO()
    workbook.save(recovered_output)
    recovered_original = recovered_output.getvalue()

    # 只拒绝预览 Task 的真实 INSERT，确认独立事务失败不抹掉已注册原件。
    with psycopg.connect(server.url) as connection:
        connection.execute(
            "CREATE FUNCTION reject_preview_submission() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN IF NEW.type='knowledge_preview' THEN "
            "RAISE EXCEPTION 'synthetic preview submission failure'; END IF; RETURN NEW; END $$"
        )
        connection.execute(
            "CREATE TRIGGER reject_preview_submission BEFORE INSERT ON tasks "
            "FOR EACH ROW EXECUTE FUNCTION reject_preview_submission()"
        )
    try:
        recovered_id, recovered_upload = upload_and_add(server, "submission-failure.xlsx", recovered_original)
        with psycopg.connect(server.url) as connection:
            registered = connection.execute(
                "SELECT filename, path, file_size FROM knowledge_files WHERE file_id=%s AND kb_id=%s",
                (recovered_id, server.kb_id),
            ).fetchone()
        assert registered == ("submission-failure.xlsx", recovered_upload["file_path"], len(recovered_original))
        assert object_bytes(server, recovered_upload["object_name"]) == recovered_original
        assert not task_rows(server, recovered_id)
    finally:
        with psycopg.connect(server.url) as connection:
            connection.execute("DROP TRIGGER reject_preview_submission ON tasks")
            connection.execute("DROP FUNCTION reject_preview_submission()")

    response = server.client.get(
        "/api/workspace/knowledge/file", params={"kb_id": server.kb_id, "file_id": recovered_id}, headers=reader
    )
    assert response.status_code == 200 and response.json()["status"] == "loading"
    recovered_tasks = wait_until(
        lambda: task_rows(server, recovered_id), lambda records: records and records[0][1] in {"success", "failed"}
    )
    assert len(recovered_tasks) == 1 and recovered_tasks[0][1] == "success", recovered_tasks
    recovered_pdf = object_bytes(server, f"{server.kb_id}/preview/{recovered_id}.pdf")
    assert "independent-submission-failure" in "".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(recovered_pdf)).pages
    )
    assert object_bytes(server, recovered_upload["object_name"]) == recovered_original
    print(json.dumps({"submission_failure_kept_original": True, "read_recovered_preview": True}))
