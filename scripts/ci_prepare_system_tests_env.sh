#!/usr/bin/env bash
# 专用 Cube CI runner 与执行节点共享 checkout 文件；不输出任何密钥。
set -euo pipefail
: "${CUBE_API_URL:?Configure the Cube runner control endpoint}"
: "${CUBE_PROXY_NODE_IP:?Configure the Cube runner data endpoint}"
test -r /dev/kvm && test -w /dev/kvm
python3 - <<'PY'
import os
from pathlib import Path

keys = ("JWT_SECRET_KEY", "API_KEY_DERIVATION_SECRET", "CUBE_API_URL", "CUBE_API_KEY", "CUBE_PROXY_NODE_IP", "CUBE_PROXY_PORT_HTTP", "CUBE_TEMPLATE_ID", "SILICONFLOW_API_KEY")
values = {key: os.environ[key] for key in keys if os.environ.get(key)}
state = Path("docker/volumes/yuxi").resolve()
values.update(CUBE_NODE_USER_DATA_DIR=str(state / "threads"), CUBE_NODE_SKILL_PROJECTION_DIR=str(state / "skill-projections"))
lines = [line for line in Path(".env.template").read_text().splitlines() if line.split("=", 1)[0] not in values]
lines.extend(f"{key}={value}" for key, value in values.items())
path = Path(".env")
path.write_text("\n".join(lines) + "\n")
path.chmod(0o600)
PY
