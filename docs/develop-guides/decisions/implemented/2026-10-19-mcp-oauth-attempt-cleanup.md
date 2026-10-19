# MCP OAuth 临时记录定期清理

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/extensions/mcp/oauth_service.py

## 问题

授权尝试和待确认结果到期后立即失效，但物理删除只由新授权请求触发。没有后续授权请求时，过期记录及其加密载荷会持续保留。

## 决策

### 实现方案

MCP OAuth service 提供独立清理事务，复用 repository 的过期查询与 `SKIP LOCKED`。现有 ARQ worker cron 在启动时及每分钟调用此入口；数据库错误沿既有事务回滚与 ARQ 失败记录处理，后续周期再次清理。授权入口保留已有顺带清理。

保留三张 MCP 表、授权有效期、连接凭据与授权确认流程；不新增配置、队列、常驻循环或通用清理框架。清理只删除已经过期且未被其他事务锁定的临时记录。

## 替代方案

- 保持仅由新授权触发：无法在停止授权流量后清除过期载荷。
- 使用 Redis TTL 或合并表：需要调整存储与原子消费边界，超出清理问题。
- 新增进程循环或接入 Run 恢复循环：重复调度机制，或把凭据清理与执行恢复健康耦合。

## 后果

调度依赖正常运行且可取得执行槽的 worker；进程停机、数据库故障或行锁持续占用会延后物理删除，逻辑到期拒绝保持生效。worker 恢复后由启动清理补处理积压。

## 验证

[OAuth 集成测试](https://github.com/xerrors/Yuxi/blob/main/backend/test/integration/services/test_mcp_oauth.py)启动独立 `YuxiWorker`，使用正式 cron 注册与每分钟周期、隔离 PostgreSQL schema 和 Redis 队列。测试只替换启动依赖和 Redis 名称，清理入口与数据库事务均使用正式实现；独立事务回读证明无新授权请求时两阶段过期载荷被删除、未过期载荷与长期连接保留、锁定记录在下一周期回收。该文件纳入 [system-tests workflow](https://github.com/xerrors/Yuxi/blob/main/.github/workflows/system-tests.yml)。

`docker compose exec -T api uv run --group test pytest test/integration/services/test_mcp_oauth.py -k worker_cleans_expired -q`：Passed，1 项。实现前执行同一用例，在缺少正式 cron 注册的断言上失败。

`docker compose exec -T api uv run --group test pytest test/integration/services/test_mcp_oauth.py -q`：Passed，44 项。`docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q`：2902 passed、97 skipped；容器缺少仓库配置文件的用例通过 `PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/test/unit/config -q` 在宿主机补跑，157 passed。

修改的 Python 文件通过 Ruff lint 与格式检查；工程契约及其 66 项测试、文档相对链接检查、`cd docs && pnpm run build` 和 `git diff --check` 均通过。

未模拟数据库断连或 worker 长期占满执行槽；这些情况沿用现有 ARQ 失败记录及后续周期调度。
