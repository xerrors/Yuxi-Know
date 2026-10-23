"""真实 Cube 场景共用的请求资源，仅回收各测试创建的数据。"""

import uuid

import pytest

from yuxi.modules.agents.runtime.sandbox.backend import UserSandboxBackend
from yuxi.modules.agents.runtime.sandbox.cube_provider import CubeSandboxProvider
from yuxi.modules.extensions.skills.projection import get_user_skills_root_dir
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.workspace.paths import ensure_user_workspace, user_workspace_dir


@pytest.fixture
def resources():
    """每个场景只创建、清理自己的用户、VM 和文件。"""
    uid = f"cube-test-{uuid.uuid4().hex}"
    password = f"Test!{uuid.uuid4().hex}"
    provider = CubeSandboxProvider()
    repo = provider.repository
    provider.adapter.health()
    ensure_user_workspace(uid)
    get_user_skills_root_dir(uid).mkdir(parents=True, exist_ok=True)
    with repo.connect() as conn:
        department = conn.execute("INSERT INTO departments(name,created_at) VALUES (%s,now()) RETURNING id", (uid,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO users(uid,username,password_hash,role,user_kind,login_failed_count,is_deleted,created_at,department_id) "
            "VALUES (%s,%s,%s,'user','human',0,0,now(),%s)",
            (uid, uid, AuthUtils.hash_password(password), department),
        )
    backend = UserSandboxBackend(uid=uid)
    backend._provider = provider
    yield uid, password, provider, backend
    with repo.user_lock(uid) as conn:
        row = repo.environment(conn, uid)
        if row and row["sandbox_id"]:
            provider.adapter.destroy(provider._reference(row))
        conn.execute("DELETE FROM sandbox_commands WHERE uid=%s", (uid,))
        conn.execute("DELETE FROM user_sandboxes WHERE uid=%s", (uid,))
        conn.execute("DELETE FROM agent_envs WHERE uid=%s", (uid,))
        conn.execute("DELETE FROM user_config WHERE uid=%s", (uid,))
        conn.execute("DELETE FROM users WHERE uid=%s", (uid,))
        conn.execute("DELETE FROM departments WHERE id=%s", (department,))
    # 文件 fixture 与身份独立，拒绝跟随任何用户创建的符号链接。
    import shutil

    shutil.rmtree(user_workspace_dir(uid).parent)
    shutil.rmtree(get_user_skills_root_dir(uid))
