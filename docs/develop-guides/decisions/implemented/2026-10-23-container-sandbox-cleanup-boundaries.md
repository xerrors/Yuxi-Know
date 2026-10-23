# Container 沙盒清理边界

状态：implemented
类型：bug-fix
Owner：backend/yuxi/sandbox_runner/manager.py

## 问题

同一 Docker daemon 上的独立部署共享受管标签，枚举和清理会跨部署。命令清空环境变量后，取消无法找到进程组；shell 正常返回也不保证后台进程结束，外部取消请求故障时不能保证命令按时停止。周期对账按 Run 名称删除旧快照时，可能误删新 attempt 的容器。

## 决策

### 实现方案

runner 从 Docker 宿主数据根派生稳定 scope，将其加入容器名称与标签。Engine 枚举必须包含 scope，manager 的直接删除和复用也校验 scope。相同数据根继续对应单 runner，不增加部署配置。

执行包装进程保留可信执行标记与独立进程组，派生并按请求期限等待实际命令。正常结束和本地超时都在 leader 退出前对组内其他进程发送 TERM/KILL，确认没有活进程后保留原退出码或返回 124；普通超时不依赖 Docker 控制请求恢复。主动取消先固定进程组，再发送 TERM/KILL 并确认该组没有活进程，不依赖子命令保留环境变量。

执行流故障且取消重试仍未确认时，runner 按不可变容器 ID 强制删除本 Run 容器并显式报错，不返回普通超时结果；这条故障兜底会中断同 Run 的其他命令。删除也失败时继续显式报错，容器仍由既有 Run 终态清理和 TTL 拥有，不新增 runner 持久状态。

provider 对账仅删除观察到的不可变容器 ID；Run 级主动取消仍由现有 Run 生命周期拥有。

## 替代方案

- 新增独立 namespace 配置：与已有数据槽位身份重复，存在漏配或复制配置导致冲突的风险。
- 普通超时直接销毁整个 Run 容器：会中断同 Run 的其他并发命令，不采用；只在执行流和局部停止均无法确认时接受整容器删除作为显式失败兜底。
- 对账继续按 Run 名称删除但携带 owner：不能保护同一 attempt 内的容器重建，使用容器 ID 更直接。

## 后果

缺少 scope 的旧容器不属于任何新 runner，升级前需等待已有 Run 收尾并清理旧容器。数据根变化会改变 scope。命令取消保持进程组边界，容器后端继续只用于单租户或可信代码。

命令多一个等待子进程的包装父进程；取消时保留已定位的进程组，即使父进程先响应 TERM 退出，仍能对忽略 TERM 的子进程升级 KILL。

可信包装进程本身失效且 Docker 控制面同时不可用时，只能依靠既有 Run 清理与 TTL 在恢复后回收；本进程内执行记录不构成跨 runner 重启的持久准入保证。

## 验证

- `backend/.venv/bin/python -m pytest backend/test/unit/sandbox -q --tb=short`：121 passed，包含执行流超期、超时与取消后断流、普通断流的停止未确认及整容器删除失败分支。
- `SANDBOX_CONTAINER_TEST=1 SANDBOX_CONTAINER_IMAGE=yuxi-sandbox:container-e2e backend/.venv/bin/python -m pytest backend/test/integration/sandbox/test_container_sandbox.py -q --tb=short`：26 passed。真实 Docker 覆盖跨部署与 attempt 隔离、正常结束、超时、取消及断流后的命令组收尾。六项收尾用例包含清空环境、忽略 TERM，以及取消和删除控制请求同时故障；响应后才发布 Workdir 触发文件，确认原命令不能再写入，而同 Run 的并发命令仍能完成产物。
- 隔离 container Compose 的 API 容器内执行 `uv run --no-sync --group test pytest test/unit -m 'not slow' -q --tb=short`：3041 passed、107 skipped。部署配置测试需要仓库根文件，另在宿主执行 `backend/.venv/bin/python -m pytest backend/test/unit/config -q --tb=short`：172 passed。
- 提供 `TEST_BASE_URL=http://127.0.0.1:5173`、同部署 PostgreSQL URL、临时测试管理员及 replay 可达地址后，执行 `backend/.venv/bin/python -m pytest backend/test/e2e/test_container_agent_execution_e2e.py -q --tb=short`：2 passed。经前端代理完成真实 API → worker → runner → PostgreSQL → Viewer 链路，回读普通完成和 steer 接续的文件、容器身份、Run 终态与清理标记，最终无残留沙盒。
- 在 `backend` 执行 `.venv/bin/ruff check yuxi`、`.venv/bin/ruff format yuxi --check`、`.venv/bin/ruff check --select I yuxi` 均通过；文档相对链接检查、`cd docs && pnpm run build`、工程契约检查及其 66 项 unittest 通过。
- 负向案例先在原实现执行：跨数据根枚举、缺少 scope 的直接删除、旧快照清理的 unit 均失败；真实 Docker 中 `exec env -i` 超时后写入文件，主动取消无法确认终止。恢复原缺陷会在对应边界上失败。
- 正常结束和控制请求故障的负控均因命令返回后继续写 Workdir 而失败；恢复普通断流不清理的分支后，两项 fresh-trigger 用例均在响应后文件写入断言失败，恢复统一收尾后通过。
- 未运行真实 Cube VM E2E、PowerShell 导出脚本或 Podman 协议验证；Docker 专项替代 PostgreSQL 准入查询，真实数据库接线由上述完整 E2E 证明。
