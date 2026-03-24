"""Tests for sandbox backend components."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import MethodType

import pytest

from deepagents.backends.protocol import ExecuteResponse, FileInfo

from yuxi.agents.backends.sandbox import (
    RemoteSandboxBackend,
    SandboxInfo,
    YuxiSandboxBackend,
    YuxiSandboxProvider,
    get_sandbox_security_opts,
    normalize_virtual_path,
)
from yuxi.agents.backends.sandbox.backend import ProvisionerSandboxBackend
from yuxi.agents.backends.sandbox import sandbox_remote as remote_sandbox_backend
from yuxi.agents.backends.composite import (
    create_agent_composite_backend,
    resolve_sandbox_backend,
    resolve_sandbox_backend_async,
)
from yuxi.agents.middlewares.skills_middleware import SkillsMiddleware


# ==================== Provider lifecycle tests ====================


def test_create_agent_composite_backend_uses_sandbox_default():
    runtime = type("RuntimeStub", (), {"context": None})()
    sandbox_backend = object()

    backend = create_agent_composite_backend(runtime, sandbox_backend=sandbox_backend)

    assert backend.default is sandbox_backend


def test_resolve_sandbox_backend_returns_none_without_thread_id():
    assert resolve_sandbox_backend("") is None


def test_resolve_sandbox_backend_returns_none_on_provider_error(monkeypatch):
    provider = type("ProviderStub", (), {"acquire": lambda self, thread_id: (_ for _ in ()).throw(RuntimeError)})()
    monkeypatch.setattr("yuxi.agents.backends.composite.get_sandbox_provider", lambda: provider)

    assert resolve_sandbox_backend("thread-1") is None


def test_resolve_sandbox_backend_async_uses_provider(monkeypatch):
    backend = object()
    provider = type("ProviderStub", (), {"acquire": lambda self, thread_id: backend})()
    monkeypatch.setattr("yuxi.agents.backends.composite.get_sandbox_provider", lambda: provider)

    assert asyncio.run(resolve_sandbox_backend_async("thread-1")) is backend


def test_destroy_stops_warm_pool_container_after_release(monkeypatch):
    provider = object.__new__(YuxiSandboxProvider)
    provider._lock = threading.Lock()
    provider._sandboxes = {}
    provider._sandbox_infos = {}
    provider._thread_sandboxes = {}
    provider._thread_locks = {}
    provider._last_activity = {}
    sandbox_key = "sandbox-1"
    thread_id = "thread-1"
    info = SandboxInfo(
        sandbox_id=sandbox_key,
        container_name="container-1",
        container_id="cid-1",
        sandbox_url="http://sandbox",
    )
    provider._warm_pool = {sandbox_key: (info, 0.0)}

    stopped = []
    provider._backend = type(
        "BackendStub",
        (),
        {"destroy": lambda self, sandbox_info: stopped.append(sandbox_info.container_id)},
    )()
    monkeypatch.setattr(provider, "_deterministic_sandbox_id", lambda _: sandbox_key)

    provider.destroy(thread_id)

    assert stopped == ["cid-1"]
    assert sandbox_key not in provider._warm_pool


def test_resolve_mount_source_maps_app_paths_under_host_project_dir(monkeypatch):
    monkeypatch.setenv("YUXI_HOST_PROJECT_DIR", "/host/project")

    resolved = YuxiSandboxProvider._resolve_mount_source(Path("/app/saves/threads/t1/user-data"))

    assert resolved == "/host/project/saves/threads/t1/user-data"


def test_remote_sandbox_backend_rejects_non_http_urls():
    with pytest.raises(ValueError):
        RemoteSandboxBackend("file:///tmp/provisioner")


def test_remote_sandbox_backend_destroy_logs_request_errors(monkeypatch):
    backend = RemoteSandboxBackend("https://provisioner.example.com")
    info = SandboxInfo(sandbox_id="sandbox-1", sandbox_url="https://sandbox.example.com")
    warnings = []

    def fake_delete(*args, **kwargs):
        raise remote_sandbox_backend.requests.RequestException("boom")

    monkeypatch.setattr(remote_sandbox_backend.requests, "delete", fake_delete)
    monkeypatch.setattr(remote_sandbox_backend.logger, "warning", warnings.append)

    backend.destroy(info)

    assert warnings


# ==================== Path compatibility tests ====================


def test_normalize_virtual_path_supports_legacy_skills_alias() -> None:
    assert normalize_virtual_path("/skills", "t-1") == "/home/yuxi/skills"
    assert normalize_virtual_path("/skills/demo/SKILL.md", "t-1") == "/home/yuxi/skills/demo/SKILL.md"


def test_normalize_virtual_path_supports_attachments_alias() -> None:
    assert normalize_virtual_path("/attachments", "thread-1") == "/home/yuxi/user-data/uploads/attachments"
    assert normalize_virtual_path("/attachments/a.md", "thread-1") == "/home/yuxi/user-data/uploads/attachments/a.md"


def test_normalize_virtual_path_supports_thread_scoped_aliases() -> None:
    assert (
        normalize_virtual_path("/outputs/thread-1/result.txt", "thread-1")
        == "/home/yuxi/user-data/outputs/result.txt"
    )
    assert normalize_virtual_path("/uploads/thread-1/demo.txt", "thread-1") == "/home/yuxi/user-data/uploads/demo.txt"
    assert (
        normalize_virtual_path("/large_tool_results/thread-1/result.json", "thread-1")
        == "/home/yuxi/user-data/large_tool_results/result.json"
    )


def test_skills_middleware_extracts_slug_for_new_and_legacy_paths() -> None:
    middleware = SkillsMiddleware()
    assert middleware.skills_sources_for_prompt == ["/home/yuxi/skills/"]
    assert middleware._extract_skill_slug_from_skill_md_path("/home/yuxi/skills/demo-skill/SKILL.md") == "demo-skill"
    assert not hasattr(middleware, "_dependency_map_cache")
    assert not hasattr(middleware, "_prompt_metadata_cache")


def test_get_sandbox_security_opts_supports_empty_and_multiple_values(monkeypatch) -> None:
    monkeypatch.setenv("YUXI_SANDBOX_SECURITY_OPTS", "")
    assert get_sandbox_security_opts() == []

    monkeypatch.setenv("YUXI_SANDBOX_SECURITY_OPTS", "seccomp=unconfined,apparmor=unconfined")
    assert get_sandbox_security_opts() == ["seccomp=unconfined", "apparmor=unconfined"]


def test_sandbox_glob_info_rebuilds_missing_path(monkeypatch) -> None:
    backend = YuxiSandboxBackend(
        sandbox_key="s-1",
        container_name="dummy",
        thread_id="t-1",
        host_user_data_dir=Path("/tmp"),
    )

    def _fake_scan_dir_info(self, path: str):
        if path.endswith("outputs"):
            return [FileInfo(path=f"{path}/result.txt", is_dir=False, size=3, modified_at="")]
        return []

    backend._scan_dir_info = MethodType(_fake_scan_dir_info, backend)
    infos = backend.glob_info("*.txt", "/home/yuxi/user-data/outputs")
    assert infos
    assert "path" in infos[0]
    assert infos[0]["path"].endswith("/result.txt")


def test_sandbox_ls_info_ignores_malformed_json_lines() -> None:
    backend = YuxiSandboxBackend(
        sandbox_key="s-1",
        container_name="dummy",
        thread_id="t-1",
        host_user_data_dir=Path("/tmp"),
    )

    def _fake_execute(self, command: str, *, timeout: int = 60):
        return ExecuteResponse(
            output="\n".join(
                [
                    '{"path": "/home/yuxi/user-data/workspace/demo.txt", "is_dir": false, "size": 3, "modified_at": ""}',
                    '{"is_dir": true}',
                    'not-json',
                ]
            ),
            exit_code=0,
            truncated=False,
        )

    backend.execute = MethodType(_fake_execute, backend)
    infos = backend.ls_info("/home/yuxi/user-data/workspace")
    assert len(infos) == 1
    assert infos[0]["path"] == "/home/yuxi/user-data/workspace/demo.txt"


def test_sandbox_user_data_root_lists_extra_files() -> None:
    backend = YuxiSandboxBackend(
        sandbox_key="s-1",
        container_name="dummy",
        thread_id="t-1",
        host_user_data_dir=Path("/tmp"),
    )

    def _fake_scan_dir_info(self, path: str):
        if path == "/home/yuxi/user-data":
            return [
                FileInfo(path="/home/yuxi/user-data/workspace", is_dir=True, size=0, modified_at=""),
                FileInfo(path="/home/yuxi/user-data/uploads", is_dir=True, size=0, modified_at=""),
                FileInfo(path="/home/yuxi/user-data/outputs", is_dir=True, size=0, modified_at=""),
                FileInfo(path="/home/yuxi/user-data/bubble_sort.py", is_dir=False, size=24, modified_at=""),
            ]
        return []

    backend._scan_dir_info = MethodType(_fake_scan_dir_info, backend)
    infos = backend.ls_info("/home/yuxi/user-data")
    paths = {item["path"] for item in infos}
    assert "/home/yuxi/user-data/workspace" in paths
    assert "/home/yuxi/user-data/uploads" in paths
    assert "/home/yuxi/user-data/outputs" in paths
    assert "/home/yuxi/user-data/bubble_sort.py" in paths


def test_provisioner_read_reports_binary_files(monkeypatch) -> None:
    backend = ProvisionerSandboxBackend(thread_id="thread-1")
    monkeypatch.setattr(backend, "_read_binary", lambda path, offset=0, limit=None: b"\x89PNG\r\n\x1a\n")

    result = backend.read("/home/yuxi/user-data/image.png")

    assert result == "Error: File '/home/yuxi/user-data/image.png' is binary and cannot be rendered as text"


def test_provisioner_read_reports_invalid_path(monkeypatch) -> None:
    backend = ProvisionerSandboxBackend(thread_id="thread-1")

    def _raise_invalid_path(path, offset=0, limit=None):
        raise ValueError("path traversal is not allowed")

    monkeypatch.setattr(backend, "_read_binary", _raise_invalid_path)

    result = backend.read("../secret.txt")

    assert result == "Error: Invalid path '../secret.txt': path traversal is not allowed"


def test_provisioner_download_files_distinguishes_invalid_path_from_read_failure(monkeypatch) -> None:
    backend = ProvisionerSandboxBackend(thread_id="thread-1")
    calls: list[str] = []

    def _fake_read_binary(path, offset=0, limit=None):
        calls.append(path)
        if path == "/bad-path":
            raise ValueError("path is required")
        raise RuntimeError("sandbox read timeout")

    monkeypatch.setattr(backend, "_read_binary", _fake_read_binary)

    responses = backend.download_files(["/bad-path", "/read-failed"])

    assert responses[0].error == "invalid_path"
    assert responses[1].error == "read_failed"
