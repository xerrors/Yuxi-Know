#!/usr/bin/env bash
# 专属测试 worker 消费真实队列；有真实用户 Run 时拒绝暂停常驻 worker。
set -euo pipefail
: "${CUBE_TEST_ISOLATED_TOPOLOGY:?Only run on a dedicated test topology without user traffic}"
[[ "$CUBE_TEST_ISOLATED_TOPOLOGY" == 1 ]]
docker compose exec -T api python - <<'PY'
from yuxi.modules.agents.repositories.sandbox import SandboxRepository
with SandboxRepository().connect() as conn:
    busy = conn.execute("SELECT count(*) AS n FROM agent_runs WHERE status IN ('pending','running','cancel_requested') OR runtime_cleanup_pending").fetchone()['n']
    busy += conn.execute("SELECT count(*) AS n FROM agent_inputs WHERE status='pending'").fetchone()['n']
    busy += conn.execute("SELECT count(*) AS n FROM background_jobs WHERE status IN ('pending','running')").fetchone()['n']
    if busy:
        raise RuntimeError('仍有 Run 或取消收尾，请在空闲拓扑执行 Cube worker 恢复验收')
PY
docker compose pause worker
restore_worker() { docker compose unpause worker >/dev/null; }
trap restore_worker EXIT
docker compose exec -T -e CUBE_TEST_OWN_WORKERS=1 api uv run --group test pytest test/e2e/test_cube_agent_execution_e2e.py -q
