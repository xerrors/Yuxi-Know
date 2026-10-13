"""runtime 与用户文件空间按各自 Owner 拒绝不可信路径。"""

from types import SimpleNamespace

import pytest
from yuxi.modules.agents.runtime.tool_approval import _normalize_runtime_path
from yuxi.modules.agents.services.artifacts import _normalize_artifact_path
from yuxi.modules.extensions.tools.builtin.sandbox_scope import resolve_runtime_sandbox_scope, runtime_scope_value
from yuxi.modules.workspace.paths import normalize_workspace_scope, validate_directory_name
from yuxi.modules.workspace.runtime_paths import normalize_artifact_path, normalize_runtime_path
from yuxi.shared.errors import PermissionDeniedError


@pytest.mark.parametrize("path", ["/a/../b", "/https://example.invalid/a", "/a\\b", "/a\0b"])
def test_path_owners_reject_the_same_invalid_bytes(path):
    """校验不能因直接 backend 或产物读取入口不同而放宽。"""
    for normalize in (normalize_runtime_path, normalize_workspace_scope):
        with pytest.raises(ValueError):
            normalize(path)
    assert _normalize_runtime_path(path) is None
    with pytest.raises(PermissionDeniedError):
        _normalize_artifact_path("/home/gem/user-data/projects/a", path)


@pytest.mark.parametrize("workdir", ["", None])
def test_artifact_read_requires_nonempty_binding(workdir):
    """用户可见 runtime 前缀不能代替当前 Workdir 绑定。"""
    with pytest.raises(ValueError, match="binding"):
        normalize_artifact_path(workdir, "/home/gem/user-data/a.txt")
    with pytest.raises(PermissionDeniedError):
        _normalize_artifact_path(workdir, "/home/gem/user-data/a.txt")


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
    assert resolve_runtime_sandbox_scope(runtime) == ("run", "owner", "projects/a")
    runtime.context = None
    with pytest.raises(ValueError, match="缺少 thread_id"):
        resolve_runtime_sandbox_scope(runtime)
    assert runtime_scope_value(runtime, "uid") is None
