"""runtime 与用户文件空间按各自 Owner 拒绝不可信路径。"""

from types import SimpleNamespace
import runpy

import pytest
from yuxi.modules.agents.runtime.tool_approval import _normalize_runtime_path
from yuxi.modules.agents.services.artifacts import _normalize_artifact_path
from yuxi.modules.extensions.tools.builtin.file_context import resolve_file_context, runtime_context_value
from yuxi.modules.workspace.paths import normalize_workspace_scope, validate_directory_name
from yuxi.modules.workspace.runtime_paths import normalize_artifact_path, normalize_runtime_path
from yuxi.shared.errors import PermissionDeniedError


def test_workspace_runtime_root_is_fixed(monkeypatch):
    """废弃前缀配置不能改变工作区与产物的唯一根。"""
    import yuxi.modules.workspace.runtime_paths as paths

    monkeypatch.setenv("SANDBOX_VIRTUAL_PATH_PREFIX", "/obsolete-root")
    namespace = runpy.run_path(paths.__file__)
    workdir = namespace["runtime_workdir_path"]("projects/a")
    assert workdir == "/home/user/workspace/projects/a"
    assert namespace["normalize_artifact_path"](workdir, f"{workdir}/report.txt") == f"{workdir}/report.txt"


@pytest.mark.parametrize("path", ["/home/gem/user-data/report.txt", "/home/gem/skills/demo/SKILL.md"])
def test_artifact_rejects_retired_runtime_roots(path):
    """已退役路径不转换为新工作区或共享 Skill 路径。"""
    with pytest.raises(ValueError, match="可见范围"):
        normalize_artifact_path("/home/user/workspace/projects/a", path)


@pytest.mark.parametrize("path", ["/a/../b", "/https://example.invalid/a", "/a\\b", "/a\0b"])
def test_path_owners_reject_the_same_invalid_bytes(path):
    """校验不能因直接 backend 或产物读取入口不同而放宽。"""
    for normalize in (normalize_runtime_path, normalize_workspace_scope):
        with pytest.raises(ValueError):
            normalize(path)
    assert _normalize_runtime_path(path) is None
    with pytest.raises(PermissionDeniedError):
        _normalize_artifact_path("/home/user/workspace/projects/a", path)


@pytest.mark.parametrize("workdir", ["", None])
def test_artifact_read_requires_nonempty_binding(workdir):
    """用户可见 runtime 前缀不能代替当前 Workdir 绑定。"""
    with pytest.raises(ValueError, match="binding"):
        normalize_artifact_path(workdir, "/home/user/workspace/a.txt")
    with pytest.raises(PermissionDeniedError):
        _normalize_artifact_path(workdir, "/home/user/workspace/a.txt")


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a\\b", "a\0b"])
def test_directory_name_is_one_component(name):
    """子目录名由共享文件边界统一拒绝路径组件。"""
    with pytest.raises(ValueError):
        validate_directory_name(name)


def test_sandbox_identity_uses_context_and_rejects_config_or_state_fallback():
    """配置及模型 state 不能替代执行者注入的身份。"""
    injected = {"uid": "owner", "thread_id": "run", "workdir_relative_path": "projects/a"}
    forged = {"uid": "other", "thread_id": "forged", "workdir_relative_path": "projects/b"}
    runtime = SimpleNamespace(context=SimpleNamespace(**injected), config={"configurable": forged}, state=forged)
    assert resolve_file_context(runtime) == ("owner", "projects/a")
    runtime.context = None
    with pytest.raises(ValueError, match="缺少 uid"):
        resolve_file_context(runtime)
    assert runtime_context_value(runtime, "uid") is None
