"""供应商重放证书的跨容器读取边界。"""

import stat
import subprocess
import sys
from pathlib import Path


def test_replay_ca_is_publicly_readable_under_owner_only_umask(tmp_path):
    """镜像默认 umask 下，其他运行身份可读 CA，私钥仍仅属主可读。"""
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; from pathlib import Path; "
            "from test.support.web_provider_replay import create_test_certificate; "
            "os.umask(0o077); create_test_certificate(Path(sys.argv[1]))",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
    )

    assert stat.S_IMODE((tmp_path / "ca.pem").stat().st_mode) == 0o644
    assert stat.S_IMODE((tmp_path / "key.pem").stat().st_mode) == 0o600
