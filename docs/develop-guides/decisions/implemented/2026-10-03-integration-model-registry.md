# Integration 测试的 ORM 装配与 Schema 锁入口

状态：implemented
类型：bug-fix
Owner：backend/test/integration/conftest.py

实现位置更新：模型注册现由 `backend/yuxi/infrastructure/postgres/models.py` 拥有，见 [2026-10-21 后端边界收敛](./2026-10-21-backend-boundary-and-provider-catalog.md)。本记录保留当次测试装配与证据。

## 问题

独立运行 后台作业 PostgreSQL 测试时，文件只导入当前用例涉及的部分 ORM 类型。SQLAlchemy 配置共享 registry 时仍需要解析 `User.agent_env` 指向的 `AgentEnv`；缺少其定义会使整个 registry 初始化失败。API、worker 和 unit 测试进程已经加载的模型不会跨进程传播，运行环境就绪不代表独立 pytest 进程已经完成装配。Schema 锁并发测试还调用了 manager 上不存在的方法，子任务提前失败，主测试等待进入事件直至超时；锁入口由 `yuxi.migrations.schema` 拥有。

## 决策

Integration 的共享 conftest 通过 session autouse fixture 调用已有 `yuxi.bootstrap.models.load_models()`，使用与 unit、Schema 初始化相同的完整模型清单。加载只注册映射，不建立数据库连接、不创建表、不启动 API 或 worker。Schema 锁测试直接调用当前 `schema_migration_lock(manager)`，使用真实 PostgreSQL 的 advisory lock，保留串行化与释放后的进入断言。

### 实现方案

测试进程经 `backend/test/integration/conftest.py` 注册全部业务与知识 ORM 后，再执行各文件的隔离 Schema 或真实 HTTP fixture。持久化连接、Schema 创建与清理仍由原 fixture 拥有；生产启动代码和模型定义不改变。`test_schema_migration_version.py` 的锁并发测试复用 schema-init 的 owning 入口，不添加 manager 兼容方法。

## 替代方案

- 在每个测试文件补齐关联模型 import：容易遗漏共享 registry 的间接关系，选择共同入口装配。
- 在通用 PostgreSQL manager 中加载所有模型：扩大生产运行时的初始化职责，此缺陷属于独立测试进程的装配，不采用。
- 只在 workflow 命令中预加载：本地直接运行单个 integration 文件仍失败，不采用。

## 后果

独立执行单个 integration 文件与批量执行都使用同一映射清单。模型加载失败会在 session fixture 初始化时明确报告；测试不依赖文件排序或之前收集的 unit 用例。

## 验证

`docker compose run --rm --no-deps -e PYTEST_ADDOPTS='-p no:cacheprovider' api uv run --no-sync pytest test/integration/services/test_durable_task_repository.py -q` 在修复前得到 16 failed、1 passed，失败原因是无法解析 `AgentEnv`；修复后在真实 PostgreSQL 的独立 Schema 中 17 passed。原测试继续断言持久 Task、lease、去重及领域终态，没有改写 oracle 或业务数据。

Ruff check 与 format 检查（使用 `backend/pyproject.toml`）通过。完整 worker assembled path 仍由更新后 GitHub Runtime System Tests 的结果证明，隔离 Schema 结果不替代它。Schema 测试修复前本地 1 failed、4 passed，失败为入口错误导致的 TimeoutError；改为真实锁入口后，后台作业 与 Schema 两文件联合执行 22 passed，包含两个真实 PostgreSQL 会话的锁竞争及释放验证。

合入 `829f65fd` 后使用上游同一 conftest 的 session autouse 装配入口，删除重复的模块级调用；模型清单与真实锁入口保持不变。
