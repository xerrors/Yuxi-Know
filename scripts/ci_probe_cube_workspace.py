"""通过正式适配器执行命令，并从宿主回读沙盒写入的字节。"""

import os
import secrets
import tempfile
from pathlib import Path

def main() -> None:
    """只创建本探针的 VM 和临时目录，结束时回收 VM。"""
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("探针仅允许在 GitHub 临时托管执行器运行")
    from yuxi.modules.agents.runtime.sandbox.cube import CubeAdapter

    adapter = CubeAdapter()
    adapter.health()
    created = []
    with tempfile.TemporaryDirectory(dir="/data/shared/yuxi-hosted-probe") as root:
        workspace = Path(root)
        # shipping 模板的 user 固定为 UID 1000；托管 runner 的 UID 不固定。
        os.chmod(workspace, 0o777)
        marker = secrets.token_hex(16)
        try:
            environment = adapter.create(
                mounts=[{"hostPath": root, "mountPath": "/home/user/workspace", "readOnly": False}],
                metadata={"purpose": "github-hosted-probe"},
                envd_token=secrets.token_urlsafe(32),
                on_created=created.append,
            )
            result = adapter.run(environment, f"printf '%s' '{marker}' > probe.txt && id -u")
            if result.exit_code != 0 or result.stdout.strip() != "1000":
                raise RuntimeError(f"普通用户执行失败: {result.exit_code}: {result.stdout!r}")
            if (workspace / "probe.txt").read_bytes() != marker.encode():
                raise RuntimeError("宿主共享文件字节与沙盒写入不一致")
            print("Cube shipping 模板、普通用户执行与宿主共享文件回读通过")
        finally:
            for environment in created:
                adapter.destroy(environment)


if __name__ == "__main__":
    main()
