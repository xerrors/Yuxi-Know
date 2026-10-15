# Run 执行使用环境变量快照

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/agents/services/runner.py

## 问题

普通命令逐条新建数据库连接读取用户环境变量。同一 Run 的命令可能因配置更新使用不同的值，短命令也重复承担连接成本。

## 决策

### 实现方案

runner 在开始执行流时使用已有异步数据库 session 读取一次用户配置，通过执行上下文供普通命令使用。快照只保留在当前执行内存中，退出时恢复上下文；文件与清理进程继续使用干净环境，无 Run 操作和手动验证读取最新配置。一次执行内的并发命令共享快照，不增加参数透传、全局缓存、Redis 或 Schema。重新领取执行的重试 attempt 重新读取配置，恢复产生的新 Run 也读取新配置；快照不写入 Run 清单、checkpoint 或日志。

## 替代方案

- 逐命令查询：实现直接，但重复建立连接且执行中的配置会漂移。
- VM 配置文件或常驻 shell：同用户并发 Run 共享环境，会覆盖彼此配置；引入密钥落盘、权限、同步和清理职责。
- 持久化每个 Run 的完整快照：可跨进程重试固定配置，但增加密钥副本及持久化生命周期；当前执行内一致性不需要这项承诺。

## 后果

已开始的执行不接收后续配置修改，包括密钥替换和删除。重试 attempt 重新读取配置；跨 attempt 固定密钥不属于当前承诺。每次执行流读取一次配置，普通命令共享该内存快照；没有沙盒命令的 Run 也读取一次，以固定生效时点。执行流沿用原有数据库 session，无新增连接池或同步数据库连接。共享 API/worker 通过显式重启加载代码。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 同一执行使用固定快照 | 中途保存使后续命令切换配置 | runner 与 provider | unit、真实 PostgreSQL/Cube 命令输出 | 读库入口拒绝执行中再次读取；修改配置后仍输出原值 | Passed |
| 上下文相互隔离并在退出后释放 | 并发 Run、后续 Run 或独立验证复用旧值 | runner | unit、真实 HTTP/Cube 集成 | 空配置不回退、异常退出、并发及后续执行 | Passed |
| 用户能判断配置生效边界 | 页面继续承诺逐命令实时加载 | 配置文档与设置卡片 | unit、lint/build、文档 build、真实 Vite 组件 DOM | 检查当前说明与实现一致 | Passed |

执行 `docker compose exec -T api uv run --group test pytest test/unit/sandbox/test_run_environment.py test/unit/services/test_agent_run_runner.py -q`：50 passed。输出断言覆盖空快照、线程与异步任务继承、两个并发上下文隔离、来源配置修改后快照不变、成功或失败后释放、下一次执行读取新配置。配置读取入口在执行中被调用时负向测试直接失败。

执行同一容器的 `pytest test/integration/sandbox/test_cube_user_environment.py -k 'env_verification or run_snapshot' -q`：3 passed。测试专属用户的真实命令输出证明快照跨保存及休眠恢复保持原值，独立 HTTP 验证读取最新值，离开上下文后新命令读取新值，最后无活动命令句柄。

同一容器的全量非 slow unit 为 2598 passed、59 skipped；现有 Agent HTTP/worker/Cube 取消与并发 E2E 为 1 passed。共享服务未重启，E2E 只作为现有服务链路回归，不能视为部署新 worker 后的快照装配验证；新 runner 装配由 unit 证明，真实执行与数据库语义由上述集成验证。未执行新版本独立 worker 的完整快照 E2E。

前端相关 7 项 unit、lint、typecheck/build、文档 build、后端改动文件 Ruff check/format 与 diff 检查通过。真实 Vite 组件以固定响应验证当前文案及 1440/768px 无横向溢出，不读取用户配置或触发保存。未重启 API/worker，未改变已有用户环境与数据。
