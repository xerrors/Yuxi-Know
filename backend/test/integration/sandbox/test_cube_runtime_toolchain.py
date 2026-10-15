"""真实普通用户的默认工具链与项目依赖验收。"""

import json

import pytest

from yuxi.modules.workspace.paths import user_workspace_dir

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.slow, pytest.mark.self_managed_resources]


def test_default_user_toolchain_supports_node_and_uv_projects(resources):
    """实际运行 Node、Python 和 uv，并从共享工作区回读脚本结果。"""
    uid, _, _, backend = resources
    versions = backend.execute(
        """python3 - <<'PY'
import json, os, shutil, subprocess, sys
tools = {name: shutil.which(name) for name in ('node', 'npm', 'npx', 'python', 'python3', 'pip', 'pip3', 'uv', 'uvx', 'git')}
print(json.dumps({'uid': os.getuid(), 'python': list(sys.version_info[:2]), 'tools': tools}))
PY""",
        timeout=60,
    )
    assert versions.exit_code == 0, versions.output
    info = json.loads(versions.output)
    assert info["uid"] != 0, info
    assert all(info["tools"].values()), info
    assert info["python"] == [3, 13], info

    result = backend.execute(
        """set -eu
node <<'JS'
const result = {major: Number(process.versions.node.split('.')[0]), uid: process.getuid()};
require('fs').writeFileSync('node-result.json', JSON.stringify(result));
JS
python -c 'import sys; assert sys.version_info[:2] == (3, 13)'
pip --version
pip3 --version
uv --version
uvx --version
uv venv .toolchain-venv
uv pip install --python .toolchain-venv/bin/python six==1.17.0
.toolchain-venv/bin/python - <<'PY'
import json, pathlib, six, sys
pathlib.Path('python-result.json').write_text(json.dumps({'python': list(sys.version_info[:2]), 'six': six.__version__}))
PY""",
        timeout=180,
    )
    assert result.exit_code == 0, result.output
    root = user_workspace_dir(uid)
    node_result = json.loads((root / "node-result.json").read_text())
    assert node_result == {"major": 24, "uid": info["uid"]}
    assert json.loads((root / "python-result.json").read_text()) == {"python": [3, 13], "six": "1.17.0"}


def test_guest_search_reports_partial_results(resources):
    """真实 Cube 的 Home 搜索保留截断信号与完整结果。"""
    _, _, _, backend = resources
    path = "/home/user/search-check.txt"
    written = backend.execute(f"printf 'needle\\nneedle\\nneedle\\n' > {path}")
    assert written.exit_code == 0, written.output
    partial = backend.grep("needle", path, max_count=2)
    assert partial.error is None and partial.truncated
    assert partial.matches == [{"path": path, "line": i, "text": "needle"} for i in (1, 2)]
    complete = backend.grep("needle", path, max_count=3)
    assert complete.error is None and not complete.truncated
    assert len(complete.matches) == 3
