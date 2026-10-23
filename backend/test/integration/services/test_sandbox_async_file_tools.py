"""真实 Sandbox 上异步文件工具的实现口径与授权边界测试。"""

from __future__ import annotations

import asyncio
import shutil
import uuid

import pytest

from yuxi.agents.backends.sandbox import ProvisionerSandboxBackend, get_sandbox_provider
from yuxi.config import get_skill_projection_dir
from yuxi.services.skills.projection import get_user_skills_root_dir
from yuxi.workspace.paths import (
    ensure_user_workspace,
    global_user_data_dir,
    user_workspace_dir,
    workspace_uid_dirname,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _create_workdir(uid: str) -> tuple[str, str]:
    """在真实 UserWorkspace 中创建测试 Workdir。"""
    ensure_user_workspace(uid)
    get_user_skills_root_dir(uid)
    workdir_id = str(uuid.uuid4())
    workdir_path = f"projects/{workdir_id}"
    (user_workspace_dir(uid) / "projects" / workdir_id).mkdir(parents=True)
    return workdir_path, f"/home/gem/user-data/{workdir_path}"


def _cleanup_user_storage(uid: str) -> None:
    """清理真实 provisioner 测试创建的 uid 级持久目录。"""
    shutil.rmtree(global_user_data_dir(uid), ignore_errors=True)
    shutil.rmtree(get_skill_projection_dir() / workspace_uid_dirname(uid), ignore_errors=True)


async def test_async_write_and_edit_use_native_sandbox_semantics():
    """异步写入/编辑必须落在原生 API 的语义上，而不是上游脚本实现。"""
    suffix = uuid.uuid4().hex
    uid = f"pytest-async-tools-{suffix}"
    workdir_path, project_root = _create_workdir(uid)
    backend = ProvisionerSandboxBackend(thread_id=uid, uid=uid, workdir_path=workdir_path)
    target = f"{project_root}/outputs/async_tools.py"
    try:
        created = await backend.awrite(target, "def main():\n    return 1\n    # tail\n")
        assert created.error is None, created.error
        assert created.path == target

        # write_file 契约是"已存在则整体替换"：模型的自我修正依赖重复写同一路径。
        replaced = await backend.awrite(target, "def main():\n    return 1\n    # tail\n")
        assert replaced.error is None, replaced.error
        after_overwrite = await backend.aread(target)
        assert after_overwrite.file_data == {"content": "def main():\n    return 1\n    # tail", "encoding": "utf-8"}

        # old+new 超过上游 50_000 字节内联阈值时，脚本实现要往 /tmp 上传，
        # 被本 backend 写权限拒绝后编辑必然失败；原生编辑器不受 payload 大小影响。
        replacement = "".join(f"    step_{index} = {index}\n" for index in range(6000)) + "    return 2\n"
        edited = await backend.aedit(target, "    return 1\n", replacement)
        assert edited.error is None, edited.error
        assert edited.occurrences == 1

        # 行窗口 read API 丢文件末尾换行，末行含换行的 old_string 必须仍能命中。
        eof_edit = await backend.aedit(target, replacement, f"{replacement}    # tail\n")
        assert eof_edit.error is None, eof_edit.error
        assert eof_edit.occurrences == 1

        # CRLF 文件：read_file 交给模型的是 LF 形态，编辑器也先归一化为 LF 再匹配并写回。
        crlf_target = f"{project_root}/outputs/crlf.md"
        await backend.awrite(crlf_target, "alpha\r\nomega\r\n")
        crlf_edit = await backend.aedit(crlf_target, "alpha\nomega", "first\nlast")
        assert crlf_edit.error is None, crlf_edit.error
        crlf_back = await backend.aread(crlf_target)
        assert crlf_back.file_data == {"content": "first\nlast", "encoding": "utf-8"}

        missing = await backend.aedit(target, "    return 404\n", "    return 5\n")
        assert missing.error == "Error: String not found in file: '    return 404\n'"

        listed = await backend.als(f"{project_root}/outputs")
        assert {item["path"] for item in listed.entries or []} == {target, crlf_target}

        globbed = await backend.aglob("**/async_tools.py", path=project_root)
        assert globbed.error is None, globbed.error
        assert [item["path"] for item in globbed.matches or []] == [target]
    finally:
        await _release(uid, workdir_path)
        _cleanup_user_storage(uid)


async def test_async_file_tools_fail_closed_before_sandbox_side_effect():
    """越界的异步调用在产生副作用前失败闭合，且不将沙箱脚本输出或他人路径内容交给模型。"""
    suffix = uuid.uuid4().hex
    uid = f"pytest-async-boundaries-{suffix}"
    workdir_path, project_root = _create_workdir(uid)
    backend = ProvisionerSandboxBackend(thread_id=uid, uid=uid, workdir_path=workdir_path)
    skill_path = "/home/gem/skills/probe/SKILL.md"
    try:
        denied_write = await backend.awrite(skill_path, "content")
        denied_edit = await backend.aedit(skill_path, "content", "other")
        assert denied_write.error == f"Error: permission denied for write on '{skill_path}'"
        assert denied_edit.error == f"Error: permission denied for write on '{skill_path}'"

        # 上游脚本实现会先执行 mkdir/读取，再把含脚本源码、Traceback 或 /etc 内容的 stdout 当作错误返回。
        for result in (denied_write, denied_edit):
            assert "python3" not in result.error
            assert "Traceback" not in result.error

        # Skill 只读投影根的宿主侧事实：越界写入不得在其中留下目录或文件。
        assert not (get_user_skills_root_dir(uid) / "probe").exists()

        denied_grep = await backend.agrep("root", path="/etc")
        denied_glob = await backend.aglob("*", path="/etc")
        denied_ls = await backend.als("/etc")
        assert denied_grep.error == "permission denied for read on '/etc'"
        assert denied_glob.error == "permission denied for read on '/etc'"
        assert denied_ls.error == "permission denied for read on '/etc'"
        assert not denied_grep.matches and not denied_glob.matches and not denied_ls.entries
        assert "/etc/" not in denied_grep.error
    finally:
        await _release(uid, workdir_path)
        _cleanup_user_storage(uid)


async def test_async_read_and_grep_hit_native_semantics_on_real_sandbox():
    """异步读取/检索在全链路真实 Sandbox 上按原生语义返回真实内容并收敛到授权根。"""
    suffix = uuid.uuid4().hex
    uid = f"pytest-async-loop-{suffix}"
    workdir_path, project_root = _create_workdir(uid)
    backend = ProvisionerSandboxBackend(thread_id=uid, uid=uid, workdir_path=workdir_path)
    target = f"{project_root}/outputs/probe.md"
    try:
        written = await backend.awrite(target, "# probe\nPGSTY_MARKER appears once\n")
        assert written.error is None, written.error

        read = await backend.aread(target)
        assert read.error is None, read.error
        assert read.file_data is not None
        assert "PGSTY_MARKER appears once" in read.file_data["content"]

        grepped = await backend.agrep("PGSTY_MARKER", path=project_root)
        assert grepped.error is None, grepped.error
        assert {"path": target, "line": 2, "text": "PGSTY_MARKER appears once"} in grepped.matches

        globbed_hits = await backend.agrep("PGSTY_MARKER", path=project_root, glob="*.md")
        assert globbed_hits.error is None, globbed_hits.error
        assert globbed_hits.matches
        globbed_misses = await backend.agrep("PGSTY_MARKER", path=project_root, glob="*.py")
        assert globbed_misses.error is None, globbed_misses.error
        assert not globbed_misses.matches

        capped = await backend.agrep("appears", path=project_root, max_count=1)
        assert capped.error is None, capped.error
        assert len(capped.matches) == 1

        globbed = await backend.aglob("**/probe.md")
        assert globbed.error is None, globbed.error
        assert target in [item["path"] for item in globbed.matches or []]

        edited = await backend.aedit(target, "appears once", "appears twice")
        assert edited.error is None, edited.error
        reread = await backend.aread(target)
        assert "appears twice" in reread.file_data["content"]

        listed = await backend.als(f"{project_root}/outputs")
        assert [item["path"] for item in listed.entries or []] == [target]
    finally:
        await _release(uid, workdir_path)
        _cleanup_user_storage(uid)


async def test_async_delete_stays_inside_write_roots_on_real_sandbox():
    """真实 Sandbox 上删除与写边界同界：授权根内成功，根外 fail-closed 且文件无损。"""
    suffix = uuid.uuid4().hex
    uid = f"pytest-async-delete-{suffix}"
    workdir_path, project_root = _create_workdir(uid)
    backend = ProvisionerSandboxBackend(thread_id=uid, uid=uid, workdir_path=workdir_path)
    outside_path = "/home/gem/scratch_delete/KEEP.txt"
    target = f"{project_root}/outputs/doomed.txt"
    try:
        created = await backend.awrite(target, "doomed")
        assert created.error is None, created.error

        deleted = await backend.adelete(target)
        assert deleted.error is None, deleted.error
        listed = await backend.als(f"{project_root}/outputs")
        assert not listed.entries

        # 授权根之外、沙箱文件系统本身可写的路径：修复前上游 rm 会真删；边界闭合后必须原样保留。
        setup = await asyncio.to_thread(
            backend.execute, f"mkdir -p /home/gem/scratch_delete && echo keep > {outside_path}"
        )
        assert setup.exit_code == 0, setup.output
        denied = await backend.adelete(outside_path)
        assert denied.error == f"Error: permission denied for write on '{outside_path}'"
        still_there = await asyncio.to_thread(backend.execute, f"test -e {outside_path} && echo KEEP")
        assert still_there.output.strip() == "KEEP"
    finally:
        await _release(uid, workdir_path)
        _cleanup_user_storage(uid)


async def _release(uid: str, workdir_path: str) -> None:
    """释放本测试创建的一次性 Sandbox。"""
    try:
        await asyncio.to_thread(
            get_sandbox_provider().release,
            uid,
            uid=uid,
            workdir_path=workdir_path,
            clear_cache_on_delete_failure=True,
        )
    except Exception:
        pass
