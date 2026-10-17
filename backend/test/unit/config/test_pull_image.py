import os
from pathlib import Path
import subprocess

import pytest

from test.unit.config._shared import project_root


@pytest.mark.parametrize("mirror_ok,origin_ok", [("1", "1"), ("0", "1"), ("0", "0")])
def test_pull_image_publishes_original_tag_only_after_success(tmp_path: Path, mirror_ok, origin_ok):
    """镜像站失效时使用原仓库，两者都失败则不产生成功标签。"""
    docker = tmp_path / "docker"
    docker.write_text("""#!/bin/bash
set -e
case "$1" in
    pull)
        if [[ "$2" == m.daocloud.io/* ]]; then
            [ "$MIRROR_OK" = 1 ] || exit 22
            echo upstream-image-digest > "$IMAGE_STATE/mirror"
        else
            [ "$ORIGIN_OK" = 1 ] || exit 23
            echo upstream-image-digest > "$IMAGE_STATE/original"
        fi ;;
    tag) cp "$IMAGE_STATE/mirror" "$IMAGE_STATE/original" ;;
    rmi) rm "$IMAGE_STATE/mirror" ;;
esac
""")
    docker.chmod(0o700)
    result = subprocess.run(
        ["bash", str(project_root() / "scripts/pull_image.sh"), "node:24-alpine"],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "IMAGE_STATE": str(tmp_path),
            "MIRROR_OK": mirror_ok,
            "ORIGIN_OK": origin_ok,
        },
        capture_output=True,
        text=True,
    )
    if mirror_ok == "0" and origin_ok == "0":
        assert result.returncode != 0
        assert not (tmp_path / "original").exists()
    else:
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "original").read_text() == "upstream-image-digest\n"
        assert not (tmp_path / "mirror").exists()
    if mirror_ok == "0":
        assert "original registry" in result.stderr


def test_pull_helper_changes_trigger_backend_unit_workflow():
    """拉取脚本单独变更也必须运行其错误路径回归。"""
    import yaml

    workflow = yaml.load((project_root() / ".github/workflows/test.yml").read_text(), Loader=yaml.BaseLoader)
    for event in ("pull_request", "push"):
        assert "scripts/pull_image.sh" in workflow["on"][event]["paths"]
