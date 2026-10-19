#!/usr/bin/env bash
# 临时托管执行器上的 Cube 与 Compose 共享状态目录；不输出密钥。
set -euo pipefail
if [[ ${GITHUB_ACTIONS:-} != true || ${RUNNER_ENVIRONMENT:-} != github-hosted ]]; then
    echo '环境准备仅允许在 GitHub 临时托管执行器运行' >&2
    exit 1
fi
python3 - <<'PY'
import ipaddress
import os
import subprocess
from pathlib import Path

keys = ("JWT_SECRET_KEY", "API_KEY_DERIVATION_SECRET", "SILICONFLOW_API_KEY", "OPENAI_REPLAY_URL", "COOPERATION_REPLAY_URL")
values = {key: os.environ[key] for key in keys if os.environ.get(key)}
gateway = str(ipaddress.IPv4Address(subprocess.check_output(
    ["docker", "network", "inspect", "bridge", "--format", "{{(index .IPAM.Config 0).Gateway}}"], text=True,
).strip()))
state = Path("/data/shared/yuxi-ci")
values.update(
    YUXI_STATE_DIR=str(state),
    CUBE_NODE_USER_DATA_DIR=str(state / "yuxi/threads"),
    CUBE_NODE_SKILL_PROJECTION_DIR=str(state / "yuxi/skill-projections"),
    CUBE_API_URL=f"http://{gateway}:3000",
    CUBE_API_KEY="",
    CUBE_PROXY_NODE_IP=gateway,
    CUBE_PROXY_PORT_HTTP="80",
    CUBE_TEMPLATE_ID="yuxi-user",
    # Cube 将 10000–19999 用作宿主临时端口，更高范围归沙盒映射和 SNAT。
    YUXI_REDIS_PORT="6380",
    YUXI_MINIO_API_PORT="9100",
    YUXI_MINIO_CONSOLE_PORT="9101",
    YUXI_MILVUS_PORT="9530",
    YUXI_MILVUS_HEALTH_PORT="9531",
)
lines = [line for line in Path(".env.template").read_text().splitlines() if line.split("=", 1)[0] not in values]
lines.extend(f"{key}={value}" for key, value in values.items())
path = Path(".env")
path.write_text("\n".join(lines) + "\n")
path.chmod(0o600)
PY
