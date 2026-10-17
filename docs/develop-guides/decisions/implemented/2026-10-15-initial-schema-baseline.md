# 当前 Schema 作为首个数据库基线

状态：implemented
类型：simplification
Owner：backend/yuxi/migrations/main.py

## 问题

当前版本以全新部署为前提，没有历史 Schema 兼容承诺。业务域和知识域的增量升级分支、历史版本编号与升级测试增加了没有当前消费者的维护成本。

## 决策

当前部署由 [app-init](2026-10-18-app-initialization.md) 调用本记录的空库基线实现并同步共享内容；运行进程只读校验版本。

### 实现方案

业务域与知识域的版本由 `infrastructure/postgres/schema.py` 拥有，当前 ORM、索引及触发器直接定义完整基线。工作区清理与工具执行收敛删除旧回收列和独立工具表，工具结果单一持久表示增加数据库约束后，业务域使用版本 4，知识域保留版本 1；工作区与工具事实的不兼容边界分别见[工作区路径清理](./2026-10-15-workspace-path-cleanup.md)、[工具执行收敛](./2026-10-15-tool-execution-convergence.md)和[工具结果表示](./2026-10-15-session-item-input-ownership.md)。删除全部 Yuxi 历史升级函数和入口分支，保留 `migrations` 包作为唯一 DDL 入口、版本记录、advisory lock、失败重试与 API/worker 只读校验。LangGraph 自有的 checkpoint setup 仍负责其初始表结构。本决定取代[沙盒环境](2026-10-15-sandbox-environment.md)、[模块审计修复](2026-10-12-module-audit-defects.md)和[远程 MCP](2026-10-03-remote-mcp-manifest.md)中的历史 Schema 升级或版本编号约定。

应用不新增通用迁移框架，也不在 app-init 中保留历史版本迁移入口。本部署现有 business=1、knowledge=1 数据库已由部署侧直接调整到当前版本，数据处置见[数据库调整记录](./2026-10-16-business-schema-v1-to-v4-migration.md)；其余旧版本由 app-init 明确拒绝。全新部署直接建立当前基线。

## 替代方案

- keep：保留历史升级链，与无历史兼容承诺的部署前提冲突。
- narrow：只删除沙盒升级，仍留下知识域升级及历史编号。
- replace：引入通用迁移框架，没有当前迁移消费者。
- remove：删除历史升级实现，保留建立完整初始 Schema 所需的机制，采用此方案。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 直接建立完整当前版本，重复运行保留数据 | 删迁移时误删当前约束或字段 | ORM、migrations | 隔离 PostgreSQL 初始化与约束回读 | 大小写同名知识库插入被拒绝，沙盒字段完整 | Passed |
| 旧 Schema 版本仍由应用入口拒绝 | schema-init 意外修改部署数据 | `migrations/main.py` | PostgreSQL integration 与入口 unit | business v1 与其他旧版本均在 DDL 前拒绝 | Passed |
| 当前数据库已符合 business v4、knowledge v1 | 数据版本与当前代码不一致 | PostgreSQL、`infrastructure/postgres/schema.py` | 部署库版本和约束回读、API/Worker readiness | schema-init 对已版本化旧库不执行 DDL | Passed |

已执行 `docker compose exec -T api uv run --group test pytest test/unit/services/test_schema_bootstrap.py test/unit/storage/test_postgres_manager_schema.py test/integration/services/test_schema_migration_version.py -q --tb=short`：21 passed，包含真实 PostgreSQL 和 LangGraph checkpoint 建表。

其余验证：

- `docker compose exec -T api uv run --group test pytest test/integration/services/test_database_relation_integrity.py test/integration/services/test_database_access_paths.py test/integration/services/test_knowledge_projection_integrity.py -q --tb=short`：22 passed，覆盖真实进程终止后的初始化恢复、关系约束和索引。
- `docker compose exec -T api uv run --group test pytest test/unit -m "not slow" -q --tb=short`：2598 passed、59 skipped；跳过项不计为通过。
- `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`：通过，后者 65 项。
- `cd docs && pnpm run build`、`git diff --check`：通过。
- 容器 `uv run ruff check` 因未安装 Ruff 无法执行；host `uv tool run ruff check` 对修改源码及入口 unit 通过，`ruff format --check` 对全部修改 Python 通过。Schema integration 文件完整 lint 仍有 9 处原有 E501；忽略 E501 后其余规则通过，新增代码无 E501。
- 已在保留现有代码的实际部署数据库执行一次性 business v1→v4 迁移，回读归档行数、工具结果、约束和退役列；API/Worker 重启后 `/api/system/ready` 为 `ready`。数据处置和备份校验详见[迁移决策](./2026-10-16-business-schema-v1-to-v4-migration.md)。

旧能力不存在：应用初始化不包含历史版本迁移脚本，只初始化空库或校验当前版本。

重新引入条件：新增来源版本时，先定义具体数据转换、失败边界和真实 PostgreSQL 证据；不得扩展为未经需求支撑的通用 migration 框架。

## 后果

未列入迁移范围的旧版本仍会被拒绝；v1 的字段与工具表处置、备份要求及回滚边界由后续迁移决策拥有。测试使用独立临时 Schema。
