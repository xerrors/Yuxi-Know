"""从真实宿主文件证明 Backend 路由与现有工具结果协议。"""

from types import SimpleNamespace

import pytest
from yuxi.modules.agents.runtime.sandbox.backend import UserSandboxBackend, create_agent_composite_backend
from yuxi.modules.workspace.paths import ensure_user_workspace, user_workspace_dir
from yuxi.modules.extensions.skills.projection import get_user_skills_root_dir
from yuxi.modules.workspace.runtime_paths import WORKSPACE_PATH, SHARED_SKILLS_PATH


@pytest.fixture
def backend(tmp_path, monkeypatch):
    """执行端一旦被访问即失败，文件结果由磁盘回读核验。"""
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "users"))
    monkeypatch.setenv("YUXI_SKILL_PROJECTION_DIR", str(tmp_path / "skills"))
    ensure_user_workspace("one")
    ensure_user_workspace("two")
    get_user_skills_root_dir("one").mkdir(parents=True)

    class NoVM:
        def __getattr__(self, key):
            raise AssertionError(f"local files must not call VM: {key}")

    value = UserSandboxBackend(uid="one")
    value._provider = NoVM()
    return value


def test_workspace_read_write_edit_and_search_do_not_wake_vm(backend):
    """写入、分页、编辑和搜索操作同一份字节。"""
    path = f"{WORKSPACE_PATH}/project/a.txt"
    assert backend.write(path, "first\nneedle\nlast\n").error is None
    root = user_workspace_dir("one")
    assert (root / "project/a.txt").read_bytes() == b"first\nneedle\nlast\n"
    page = backend.read(path, offset=1, limit=1)
    assert page.file_data["content"] == "needle\n"
    assert (page.start_line, page.end_line, page.next_offset) == (2, 2, 2)
    assert backend.edit(path, "needle", "changed").occurrences == 1
    assert (root / "project/a.txt").read_bytes() == b"first\nchanged\nlast\n"
    assert backend.grep("changed", f"{WORKSPACE_PATH}/project").matches == [{"path": path, "line": 2, "text": "changed"}]
    assert [item["path"] for item in backend.glob("*.txt", f"{WORKSPACE_PATH}/project").matches] == [path]
    assert backend.read("/home/user/workspace/project/a.txt").file_data["content"].startswith("first")


def test_workspace_write_cannot_overwrite_existing_file(backend):
    """新建工具不覆盖文件。"""
    path = f"{WORKSPACE_PATH}/exists.txt"
    assert backend.write(path, "original").error is None
    assert backend.write(path, "replacement").error
    assert (user_workspace_dir("one") / "exists.txt").read_text() == "original"


def test_symlink_cannot_escape_to_other_user_and_never_falls_back(backend):
    """恢复 symlink 缺陷会泄露另一用户字节。"""
    other = user_workspace_dir("two")
    (other / "secret.txt").write_text("other-user-secret")
    root = user_workspace_dir("one")
    (root / "escape").symlink_to(other, target_is_directory=True)
    path = f"{WORKSPACE_PATH}/escape/secret.txt"
    assert backend.read(path).error
    assert backend.write(path, "modified").error
    assert (other / "secret.txt").read_text() == "other-user-secret"
    assert backend.glob("*", WORKSPACE_PATH).error is None


def test_shared_skills_read_only_without_vm(backend):
    """授权投影可读且所有模型写入方法拒绝修改。"""
    source = get_user_skills_root_dir("one") / "demo"
    source.mkdir()
    (source / "SKILL.md").write_text("shared")
    path = f"{SHARED_SKILLS_PATH}/demo/SKILL.md"
    assert backend.read(path).file_data["content"] == "shared"
    assert backend.edit(path, "shared", "modified").error
    assert backend.upload_files([(path, b"modified")])[0].error
    assert (source / "SKILL.md").read_text() == "shared"


def test_artifact_must_be_workspace_regular_file(backend):
    """展示 Home 文件不会隐式恢复 VM。"""
    assert not backend.regular_file_exists("/home/user/.config/example")
    path = f"{WORKSPACE_PATH}/result.txt"
    backend.write(path, "result")
    assert backend.regular_file_exists(path)
    (user_workspace_dir("one") / "link.txt").symlink_to("result.txt")
    assert not backend.regular_file_exists(f"{WORKSPACE_PATH}/link.txt")


def test_composite_keeps_artifacts_root_and_user_identity(backend):
    """Backend 装配仍向摘要和文件工具提供相同产物根。"""
    context = SimpleNamespace(uid="one", runtime_scope_id="scope", workdir_relative_path="projects/11111111-1111-4111-8111-111111111111")
    result = create_agent_composite_backend(context)
    assert result.default.id == "one"
    assert result.artifacts_root == f"{WORKSPACE_PATH}/{context.workdir_relative_path}/outputs"


@pytest.mark.parametrize("path", ["/home/user/workspace/../two/secret", "https://host/a", "/home/user/workspace/a\\b"])
def test_invalid_path_has_no_filesystem_side_effect(backend, path):
    """词法越界和对象 URL 不进入文件执行边界。"""
    assert backend.write(path, "invalid").error


@pytest.mark.parametrize("count, limit", [(3, 2), (1001, None), (2, 2)])
def test_guest_search_reports_truncation_from_actual_file(backend, tmp_path, monkeypatch, count, limit):
    """Guest 搜索执行真实脚本，超限与完整结果必须可区分。"""
    import subprocess

    source = tmp_path / "guest.txt"
    source.write_text("needle\n" * count)

    def execute(command):
        """在独立临时目录执行 Guest 脚本并回读标准输出。"""
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        return SimpleNamespace(exit_code=result.returncode, output=result.stdout, truncated=False)

    monkeypatch.setattr(backend, "execute", execute)
    result = backend.grep("needle", str(source), max_count=limit)
    assert result.error is None
    assert len(result.matches) == min(count, limit or 1000)
    assert result.truncated is (count > (limit or 1000))
