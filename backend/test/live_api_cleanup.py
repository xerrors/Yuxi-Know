from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import asyncpg
import httpx
from yuxi import config as conf

PYTEST_RESOURCE_PREFIXES = ("pytest", "py_test")
E2E_THREAD_TEST_MARKERS = frozenset(
    {
        "agent-async-e2e",
        "agent-sync-e2e",
        "agent-steer-e2e",
        "attachment-state-e2e",
        "ocr-config-e2e",
        "personal-skill-e2e",
        "read-file-e2e",
        "subagent-stream-e2e",
        "viewer-fs-e2e",
    }
)
E2E_AGENT_SLUG_PREFIXES = (
    "e2e-agent-call-",
    "e2e-async-agent-",
    "e2e-main-",
    "e2e-personal-skill-",
    "e2e-read-file-",
    "e2e-steer-agent-",
    "e2e-subagent-",
    "e2e-sync-agent-",
    "pytest-personal-agent-",
)
SAFE_THREAD_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _is_pytest_resource(name: object) -> bool:
    """判断资源名称是否属于 pytest 约定的测试数据。"""

    return isinstance(name, str) and name.casefold().startswith(PYTEST_RESOURCE_PREFIXES)


def _has_prefix(value: object, prefixes: tuple[str, ...]) -> bool:
    """判断字符串是否以任一约定前缀开头。"""

    return isinstance(value, str) and value.startswith(prefixes)


def _is_e2e_thread(thread: object) -> bool:
    """只识别测试显式写入的 E2E 标记，不按用户可控标题猜测资源。"""

    if not isinstance(thread, dict):
        return False

    metadata = thread.get("metadata")
    if not isinstance(metadata, dict):
        return False
    if metadata.get("_yuxi_e2e") is not True:
        return False
    return metadata.get("test") in E2E_THREAD_TEST_MARKERS or _has_prefix(
        metadata.get("marker"), ("YUXI_SUBAGENT_STREAM_E2E_",)
    )


def _is_e2e_agent(agent: object, owner_uid: str) -> bool:
    """判断智能体是否是当前清理用户创建的 E2E 临时智能体。"""

    if not isinstance(agent, dict):
        return False
    slug = agent.get("slug") or agent.get("agent_id") or agent.get("id")
    return _has_prefix(slug, E2E_AGENT_SLUG_PREFIXES) and str(agent.get("created_by") or "") == owner_uid


def _resolve_e2e_thread_storage(thread_id: str) -> Path:
    """校验并返回测试线程的独立沙盒目录，不触碰用户共享工作区。"""

    if not SAFE_THREAD_ID.fullmatch(thread_id):
        raise RuntimeError(f"E2E conversation cleanup received an unsafe thread id: {thread_id!r}")
    if thread_id == "shared":
        raise RuntimeError("E2E conversation cleanup refuses to target the shared workspace")

    threads_root = (Path(conf.save_dir) / "threads").resolve()
    raw_thread_root = threads_root / thread_id
    if raw_thread_root.is_symlink():
        raise RuntimeError(f"E2E conversation cleanup refuses to remove symlink: {raw_thread_root}")

    thread_root = raw_thread_root.resolve()
    if thread_root.parent != threads_root:
        raise RuntimeError(f"E2E conversation cleanup path escaped thread root: {thread_root}")
    return thread_root


def remove_e2e_thread_storage(thread_id: str) -> None:
    """删除测试线程的独立沙盒目录。"""

    thread_root = _resolve_e2e_thread_storage(thread_id)
    if thread_root.is_dir():
        shutil.rmtree(thread_root)


async def _list_e2e_thread_statuses(owner_uid: str) -> dict[str, str]:
    """读取当前 E2E 用户的已标记线程及其子智能体线程状态。"""

    postgres_url = os.getenv("POSTGRES_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/yuxi")
    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            "SELECT id, thread_id, status, extra_metadata FROM conversations WHERE uid = $1",
            owner_uid,
        )
        marked_parent_ids: list[int] = []
        statuses: dict[str, str] = {}
        for row in rows:
            metadata = row["extra_metadata"]
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = None
            if not isinstance(metadata, dict) or metadata.get("_yuxi_e2e") is not True:
                continue
            marked_parent_ids.append(int(row["id"]))
            statuses[str(row["thread_id"])] = str(row["status"] or "")

        if marked_parent_ids:
            child_rows = await conn.fetch(
                """
                SELECT st.child_thread_id, child.status
                FROM subagent_threads st
                JOIN conversations child ON child.id = st.child_conversation_id
                WHERE st.parent_conversation_id = ANY($1::int[])
                """,
                marked_parent_ids,
            )
            statuses.update({str(row["child_thread_id"]): str(row["status"] or "") for row in child_rows})
        return statuses
    finally:
        await conn.close()


async def cleanup_e2e_chat_resources(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    owner_uid: str,
    thread_storage_statuses: dict[str, str] | None = None,
) -> None:
    """删除 E2E 产生的对话和临时智能体，避免测试数据污染最近对话。"""

    page_size = 500
    offset = 0
    threads: list[dict] = []
    seen_thread_ids: set[str] = set()
    while True:
        threads_response = await client.get(
            "/api/chat/threads",
            params={"limit": page_size, "offset": offset},
            headers=headers,
        )
        if threads_response.status_code != 200:
            raise RuntimeError(f"Failed to list E2E conversations for cleanup: {threads_response.text}")

        page = threads_response.json()
        if not isinstance(page, list):
            raise RuntimeError("E2E conversation cleanup response must be a list")
        threads.extend(
            thread
            for thread in page
            if isinstance(thread, dict)
            and str(thread.get("id") or thread.get("thread_id") or "") not in seen_thread_ids
        )
        seen_thread_ids.update(
            str(thread.get("id") or thread.get("thread_id"))
            for thread in page
            if isinstance(thread, dict) and (thread.get("id") or thread.get("thread_id"))
        )

        non_pinned_count = sum(not bool(thread.get("is_pinned")) for thread in page if isinstance(thread, dict))
        if len(page) < page_size or non_pinned_count == 0:
            break
        offset += non_pinned_count

    failures: list[str] = []
    deleted_thread_ids: set[str] = set()
    for thread in threads:
        if not _is_e2e_thread(thread):
            continue
        thread_id = None
        if isinstance(thread, dict):
            thread_id = thread.get("id") or thread.get("thread_id")
        if not thread_id:
            failures.append("E2E conversation cleanup entry is missing thread id")
            continue

        try:
            _resolve_e2e_thread_storage(str(thread_id))
        except (OSError, RuntimeError) as exc:
            failures.append(f"Invalid E2E conversation storage {thread_id}: {exc}")
            continue

        delete_response = await client.delete(f"/api/chat/thread/{thread_id}", headers=headers)
        if delete_response.status_code not in {200, 404}:
            failures.append(f"Failed to delete E2E conversation {thread_id}: {delete_response.text}")
            continue
        try:
            remove_e2e_thread_storage(str(thread_id))
        except (OSError, RuntimeError) as exc:
            failures.append(f"Failed to delete E2E conversation storage {thread_id}: {exc}")
        deleted_thread_ids.add(str(thread_id))

    if thread_storage_statuses is None:
        try:
            thread_storage_statuses = await _list_e2e_thread_statuses(owner_uid)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"Failed to list persisted E2E conversation resources: {exc}")
            thread_storage_statuses = {}

    for thread_id, status in thread_storage_statuses.items():
        if thread_id in deleted_thread_ids:
            continue
        try:
            _resolve_e2e_thread_storage(thread_id)
        except (OSError, RuntimeError) as exc:
            failures.append(f"Invalid persisted E2E conversation storage {thread_id}: {exc}")
            continue

        if status not in {"deleted", ""}:
            delete_response = await client.delete(f"/api/chat/thread/{thread_id}", headers=headers)
            if delete_response.status_code not in {200, 404}:
                failures.append(f"Failed to delete persisted E2E conversation {thread_id}: {delete_response.text}")
                continue
        try:
            remove_e2e_thread_storage(thread_id)
        except (OSError, RuntimeError) as exc:
            failures.append(f"Failed to delete persisted E2E conversation storage {thread_id}: {exc}")

    agents_response = await client.get(
        "/api/agent",
        params={"include_subagents": "true"},
        headers=headers,
    )
    if agents_response.status_code != 200:
        failures.append(f"Failed to list E2E agents for cleanup: {agents_response.text}")
    else:
        payload = agents_response.json()
        agents = payload.get("agents") if isinstance(payload, dict) else None
        if not isinstance(agents, list):
            failures.append("E2E agent cleanup response is missing an agents list")
        else:
            for agent in agents:
                if not _is_e2e_agent(agent, owner_uid):
                    continue
                agent_slug = agent.get("slug") or agent.get("agent_id") or agent.get("id")
                if not agent_slug:
                    failures.append("E2E agent cleanup entry is missing agent slug")
                    continue
                delete_response = await client.delete(f"/api/agent/{agent_slug}", headers=headers)
                if delete_response.status_code not in {200, 404}:
                    failures.append(f"Failed to delete E2E agent {agent_slug}: {delete_response.text}")

    if failures:
        raise RuntimeError("; ".join(failures))


async def cleanup_pytest_knowledge_resources(
    client: httpx.AsyncClient,
    headers: dict[str, str],
) -> None:
    """通过公开 API 删除 pytest 前缀的评估资源和知识库。"""

    list_response = await client.get("/api/knowledge/databases", headers=headers)
    if list_response.status_code != 200:
        raise RuntimeError(f"Failed to list knowledge databases for cleanup: {list_response.text}")

    payload = list_response.json()
    if payload.get("message"):
        raise RuntimeError(f"Failed to list knowledge databases for cleanup: {payload['message']}")

    databases = payload.get("databases")
    if not isinstance(databases, list):
        raise RuntimeError("Knowledge database cleanup response is missing a databases list")

    failures: list[str] = []
    for database in databases:
        kb_id = database.get("kb_id") if isinstance(database, dict) else None
        if not kb_id:
            failures.append("Knowledge database cleanup entry is missing kb_id")
            continue

        resource_specs = (
            (f"/api/evaluation/databases/{kb_id}/runs", "run_id", f"/api/evaluation/databases/{kb_id}/runs"),
            (f"/api/evaluation/databases/{kb_id}/datasets", "dataset_id", "/api/evaluation/datasets"),
        )
        for list_path, id_field, delete_prefix in resource_specs:
            response = await client.get(list_path, headers=headers)
            if response.status_code != 200:
                failures.append(f"Failed to list evaluation resources for {kb_id}: {response.text}")
                continue

            resources = response.json().get("data")
            if not isinstance(resources, list):
                failures.append(f"Evaluation cleanup response for {kb_id} is missing a data list")
                continue

            for resource in resources:
                if not isinstance(resource, dict) or not _is_pytest_resource(resource.get("name")):
                    continue
                resource_id = resource.get(id_field)
                if not resource_id:
                    failures.append(f"Evaluation cleanup resource for {kb_id} is missing {id_field}")
                    continue

                delete_response = await client.delete(f"{delete_prefix}/{resource_id}", headers=headers)
                if delete_response.status_code not in {200, 404}:
                    failures.append(f"Failed to delete evaluation resource {resource_id}: {delete_response.text}")

    for database in databases:
        if not isinstance(database, dict) or not _is_pytest_resource(database.get("name")):
            continue
        kb_id = database.get("kb_id")
        if not kb_id:
            continue

        delete_response = await client.delete(f"/api/knowledge/databases/{kb_id}", headers=headers)
        if delete_response.status_code not in {200, 404}:
            failures.append(f"Failed to delete knowledge database {kb_id}: {delete_response.text}")

    if failures:
        raise RuntimeError("; ".join(failures))
