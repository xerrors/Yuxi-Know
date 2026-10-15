# 当前 Schema 作为首个数据库基线

状态：implemented
类型：simplification
Owner：backend/yuxi/migrations/main.py

## 问题

当前版本以全新部署为前提，没有历史 Schema 兼容承诺。业务域和知识域的增量升级分支、历史版本编号与升级测试增加了没有当前消费者的维护成本。

## 决策

### 实现方案

业务域与知识域的版本由 `infrastructure/postgres/schema.py` 拥有，当前 ORM、索引及触发器直接定义完整基线。工作区清理删除旧回收列后，业务域使用版本 2，知识域保留版本 1；具体不兼容边界见[工作区路径清理](./2026-10-15-workspace-path-cleanup.md)。删除全部 Yuxi 历史升级函数和入口分支，保留 `migrations` 包作为唯一 DDL 入口、版本记录、advisory lock、失败重试与 API/worker 只读校验。LangGraph 自有的 checkpoint setup 仍负责其初始表结构。本决定取代[沙盒环境](2026-10-15-sandbox-environment.md)、[模块审计修复](2026-10-12-module-audit-defects.md)和[远程 MCP](2026-10-03-remote-mcp-manifest.md)中的历史 Schema 升级或版本编号约定。

应用不修改已有运行数据库，不新增迁移框架。非当前版本明确拒绝初始化。部署者使用独立空库启动首个基线。

## 替代方案

- keep：保留历史升级链，与无历史兼容承诺的部署前提冲突。
- narrow：只删除沙盒升级，仍留下知识域升级及历史编号。
- replace：引入通用迁移框架，没有当前迁移消费者。
- remove：删除历史升级实现，保留建立完整初始 Schema 所需的机制，采用此方案。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 直接建立完整当前版本，重复运行保留数据 | 删迁移时误删当前约束或字段 | ORM、migrations | 隔离 PostgreSQL 初始化与约束回读 | 大小写同名知识库插入被拒绝，沙盒字段完整 | Passed |
| 非当前版本在 DDL 前拒绝 | 旧升级入口仍可达 | migrations/main.py | PostgreSQL 与入口 unit | 不兼容版本、未版本化非空库；回读原数据 | Passed |
| 旧升级能力不存在 | 残留函数、调用及升级文档 | migrations、部署参考 | 符号搜索、工程检查与文档 build | 恢复任一历史升级分支 | Inspected |

已执行 `docker compose exec -T api uv run --group test pytest test/unit/services/test_schema_bootstrap.py test/unit/storage/test_postgres_manager_schema.py test/integration/services/test_schema_migration_version.py -q --tb=short`：21 passed，包含真实 PostgreSQL 和 LangGraph checkpoint 建表。

其余验证：

- `docker compose exec -T api uv run --group test pytest test/integration/services/test_database_relation_integrity.py test/integration/services/test_database_access_paths.py test/integration/services/test_knowledge_projection_integrity.py -q --tb=short`：22 passed，覆盖真实进程终止后的初始化恢复、关系约束和索引。
- `docker compose exec -T api uv run --group test pytest test/unit -m "not slow" -q --tb=short`：2598 passed、59 skipped；跳过项不计为通过。
- `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`：通过，后者 65 项。
- `cd docs && pnpm run build`、`git diff --check`：通过。
- 容器 `uv run ruff check` 因未安装 Ruff 无法执行；host `uv tool run ruff check` 对修改源码及入口 unit 通过，`ruff format --check` 对全部修改 Python 通过。Schema integration 文件完整 lint 仍有 9 处原有 E501；忽略 E501 后其余规则通过，新增代码无 E501。
- Not run：共享运行库的 HTTP/worker E2E；本任务不替换已有数据库或版本标记，直接证据来自隔离 PostgreSQL 初始化及相关数据库回归。

旧能力不存在：删除知识名称、用户沙盒和休眠时间的增量升级函数、入口调用及专用升级测试。

重新引入条件：首个正式基线之后出现明确需要保留的数据和 Schema 演进需求，再定义版本迁移及真实数据库证据。

## 后果

现有带历史版本标记的开发库不匹配新基线，重启会被校验拒绝；本任务不改写版本标记或清理运行数据。测试使用独立临时 Schema。
