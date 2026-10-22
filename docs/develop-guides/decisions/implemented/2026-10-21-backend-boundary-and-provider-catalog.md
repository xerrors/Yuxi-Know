# 后端边界收敛与网页供应商目录

状态：implemented
类型：architecture
Owner：backend/yuxi/infrastructure/postgres/models.py

## 问题

架构审计列出的反向依赖和重复目录在当前分支真实存在：`migrations` 为了取得 ORM metadata 反向导入 `bootstrap.models`，而 `bootstrap/app.py` 又调用 migrations；`system/options.py` 汇总 `extensions.options`，同时 extensions 的网页服务读取 system 配置；`infrastructure/oidc/client.py` 从 `modules.identity` 取协议常量。网页供应商的身份、凭据变量、端点和启用的抓取能力分散在后端 Option 定义、运行时分支和前端常量表。知识文档解析/入库作业的提交在路由内维护两份近似 helper，identity、departments、API Key、agent 和 evaluation 的若干读路由直接构造 repository。前端容器使用 Node 24，而 CI 门禁使用 Node 22。

范围边界：`PostgresManager.async_check_first_run` 在当前 HEAD 已不存在；文件、URL 与工作区导入已共用 `services/uploads.py` 的 `stage_document`，不再各自重复哈希、去重和对象写入。本轮不重新引入这两项。

## 决策

流程说明：本变更是对既有架构审计所列边界的直接收敛，没有待裁决的产品取舍、外部状态变更或兼容承诺；实现、替代方案与验证在同一变更中闭合，因此按同一变更内生效的 implemented 记录，不单独创建 proposed。

### 实现方案

- ORM 注册由 `infrastructure/postgres/models.py` 拥有，保留按模块名惰性导入的单一清单。`migrations`、`bootstrap/app.py`、测试与脚本从该模块取得 metadata；`bootstrap/models.py` 删除，`bootstrap → migrations` 保持单向。
- 跨域配置定义汇总移到 `bootstrap/options.py`。`modules/system/options.py` 只保留系统级默认配置（含默认网页供应商）；默认网页供应商的凭据检查移到 system HTTP 适配层，system 服务不再导入 extensions。
- `MAX_TOKEN_AGE` 由 `infrastructure/oidc/client.py` 拥有，identity repository 依赖 infrastructure，不再反向导入身份模块。
- `shared/web_providers.py` 保存供应商 id、名称、环境变量、官方端点和是否支持抓取。`extensions/options.py` 从目录派生配置定义及 `params.provider` 元数据；`extensions/web/providers.py` 拥有搜索/抓取的 payload、结果解析和端点选择；`system/options.py` 的默认供应商 choices 也从目录派生；前端设置页从 `/config/options` 返回的 `params.provider` 派生卡片，不再维护独立的供应商常量表。
- 文档解析/入库作业提交移到 `modules/knowledge/services/document_actions.py`，路由保留参数校验、权限依赖和 HTTP 响应映射。
- identity 用户、部门、API Key、agent 定义、evaluation 数据集和 Skill 列表的只读路由改为调用各自 service；权限判断和 404/400 等 HTTP 映射仍在路由。
- 前端 Docker 的 development/build 阶段统一为 `node:22-alpine`，与 CI 和本机验证版本一致；离线镜像导出列表同步更新。

### 边界说明

`infrastructure/postgres/models.py` 只是 ORM 注册清单，使用 `import_module` 按名称加载，不提供业务查询或领域用例；它知道模型模块名，但不依赖其服务实现。若未来新增持久化后端，仍以该清单为唯一注册入口。

## 替代方案

- 保留 `bootstrap/models.py`，把 metadata 注入 migrations 的每个 DDL 函数：可保持组合根，但需要把调用约定扩散到大量测试 fixture，且当前清单仍会在 app 入口与 migrations 之间重复调用。本轮采用持久化注册清单。
- 让 migrations 继续导入 bootstrap：直接保留依赖环，不采用。
- 保留三份供应商目录并增加一致性测试：仍要求新增供应商修改三处后端与一处前端代码；本轮由单一目录和配置元数据派生替代。
- 保留路由直接读 repository：HTTP 适配层会持续绑定持久化细节，测试也需要按路由分叉；本轮只收敛审计列出的只读入口。

## 后果

新增供应商只需修改 `shared/web_providers.py` 的目录项和 `extensions/web/providers.py` 的请求/响应适配；配置定义、默认选项、前端卡片和目录一致性测试随之派生。已有持久化 Option 记录在 app-init 下次同步时获得 `params.provider`，旧记录不会阻塞启动。ORM 注册清单位于 infrastructure，新增模型模块必须同步加入，否则 Schema 初始化与测试装配都会缺少映射。路由的权限与 HTTP 错误映射保持原状，未引入新的授权路径或兼容层。

## 验证

旧能力不存在：`bootstrap/models.py`、`system/options.py` 的跨域汇总、`infrastructure/oidc` 对 identity 的反向导入、前端硬编码供应商表和路由内重复的解析/入库作业 payload 构造均不存在；新增静态边界测试覆盖前三项与 ORM 清单位置，前端目录派生由前端 unit 覆盖。

重新引入条件：只有在持久化注册被新的组合机制替代，或供应商协议需要与配置目录分离部署时，才重新评估对应边界；重新引入必须同时更新本记录和负向边界测试。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| migrations 不再依赖 bootstrap，ORM 清单唯一 | 组合根与 Schema 初始化成环、模型漏注册 | infrastructure/postgres/models.py | 新增静态依赖测试、unit/config | 在 migrations 重新导入 bootstrap 使测试失败 | Passed：5 项边界测试 |
| system 不再汇总 extensions 配置 | 跨域汇总回到 system、凭据校验散落 | bootstrap/options.py、modules/system | unit/config、web provider 单测 | `system/options.py` 导入 extensions 使测试失败 | Passed：39 项 provider 单测 |
| 网页供应商目录单一且前端派生 | 新增供应商漏改端点、选项或前端卡片 | shared/web_providers.py | 目录一致性测试、前端 unit | Option 元数据与目录不一致使测试失败 | Passed：后端 39 项、前端 3 项 |
| 文档作业提交离开路由 | 两份 payload helper 漂移 | modules/knowledge/services/document_actions.py | 知识路由 unit | 恢复路由内 payload 构造并破坏 pending 参数使测试失败 | Passed：19 项知识文档路由测试 |
| 只读路由通过 service 访问持久化 | 路由重新绑定 repository | identity/agents/evaluation/skills services | 路由 unit、真实 HTTP integration（未在本机执行） | 在路由重新构造 repository 使对应替换测试失效 | 部分：14 项 identity/API Key、6 项 system、2 项 agent、6 项 Skill 路由 unit 通过；integration 未执行 |

- `uv run --group test ruff check yuxi test/unit/config/test_backend_module_boundaries.py`：通过。
- `uv run --group test pytest test/unit/routers/test_agent_management.py test/unit/routers/test_knowledge_resource_permission.py test/unit/routers/test_auth_router_cli_auth.py test/unit/routers/test_system_router.py test/unit/routers/test_knowledge_documents_router.py test/unit/routers/test_http_exception_passthrough.py test/unit/agents/test_web_search_provider.py -q`：116 passed。
- `uv run --group test pytest test/unit/routers/test_api_key_security.py test/unit/routers/test_system_router.py -q`：16 passed。
- 完整 `uv run --group test pytest test/unit -m "not slow" -q`：3088 passed。
- CI 精确 Ruff 命令（`ruff check yuxi`、`ruff format yuxi --check`、`ruff check --select I yuxi`）：通过；同时修复了基线中 5 个未排序的 agents 服务导入和 seed 脚本导入顺序。
- 前端 `pnpm run lint:check && pnpm run test:unit && pnpm run build`：lint 通过，770 项 unit 通过，生产构建通过（仅既有 chunk 体积警告）。
- 文档 `pnpm run build`：通过（8.18s）。工程信任检查：252 decisions / 6 workflows / 4 agents files / 416 docs / 41 routers / 293 frontend sources；检查器 66 项 unit 通过。
- 未执行 Docker Compose、真实 PostgreSQL integration、浏览器 E2E 与构建镜像；本机无 docker CLI。Node 版本仅做静态统一，未重新构建镜像。
