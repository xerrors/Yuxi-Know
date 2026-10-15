# Session 输入、工具结果和执行收尾收敛

状态：implemented
类型：simplification
Owner：ARCHITECTURE.md

## 问题

历史 item、进行中分组和展示消息重复维护，输入提交分散于页面、命令和 API 层；工具结果同时保存文本与结构化输出，完成和取消重复维护收尾时序。统计查询重复扫描相同数据，CI 和本地重复选择部分 E2E。

## 决策

### 实现方案

| 责任与 Owner | 保留的实现 | 删除的实现 |
|---|---|---|
| Thread item / sessionRuntime | 每 Thread 一份 item reducer，历史分页、SSE 与恢复快照合并后派生展示 | historyItems、ongoingRunGroup、历史事件二次同步、页面三组历史/进行中合并 helper、无消费者的 ThreadMessageList |
| 完整输入 / sessionInput、队列观察者 | 冻结载荷、接收与幂等重试由 sessionInput 拥有；接收后由队列观察者唯一启动 Run | 页面内提交流程、submitSessionInput、API postSessionEvents 回执恢复、提交后的第二次 Input 查询与流控制 |
| 工具结果 / tool_audit、tool_results | extra_metadata.output 保存唯一原始结果，审计、Memory、引用标注与公开内容由它派生 | 工具终态写入 content 参数及第二份正文；数据库约束禁止 tool_audit.content 非空，business 版本 4 拒绝旧库 |
| Run 收尾 / runner | _settle_uncommitted_run 合并未提交失败与用户取消，已提交执行结果复用统一清理与通知边界 | _finish_run、_finish_user_cancel 的重复流程；等待和 yield 保留领域语义 |
| 工具统计 / dashboard repository | 一次按工具、执行状态、滚动日桶聚合 | 多次扫描同一工具审计事实；保留七个 24 小时窗口的原有边界 |
| 测试编排 / run_tests.sh、既有 conftest | CI 与本地复用唯一 E2E selector，反馈测试复用独占 replay fixture | CI 重复执行的反馈、可见工具、Key scope、OpenAI 事件步骤及反馈文件内重复服务器 fixture |

新增源码文件仅有 sessionInput.js，替代上表列出的旧提交实现。其测试并入既有 sessionCommands.test.js，页面验收并入 sessionHistoryLoading.js，删除重复的 Vite/API 与浏览器协议 fixture。

独立 Python 测试运行器及其进程、数据库、Redis、目录状态管理没有替代现有 Compose/CI 生命周期，撤下运行器及其专用测试。隔离环境继续由既有 Compose 槽位拥有；测试脚本只选择和执行套件。

### 测试资产的替代关系

| 删除或合并的资产 | 当前证据 Owner 与保留的独有行为 |
|---|---|
| agentRun.test.js 与仅被它引用的 agentRun.js | 共享 runtime 和 agentRunEvents.test.js 拥有当前 Run 的 steer 能力；旧 Chat/source 判据没有生产消费者 |
| agentThreadQueueTransition.test.js、Run 事件文件中的 FIFO 用例 | agentInputQueue.test.js 统一拥有领取后的 item/Turn 归属、监视器保留、重置和释放；消息分组用例回到 messageGrouping.test.js |
| chatStartScreen.test.js、sessionModelBinding.test.js | sessionWorkspaceVisibility.test.js 保留真实视图片段渲染和响应式切换；threadCreation.test.js 执行实际 agent、model 与路由选择逻辑，替代源码字符串和顺序断言 |
| agentInputAreaCompositionGuard.test.js、actionDropdownKeyboard.test.js | 既有 sessionHistoryLoading.js 与 actionDropdownGrowth.js 分别观察输入法回车不发送、Escape 关闭弹层且阻止默认行为与冒泡 |
| test_agent_call_entrypoints_e2e.py | 确定性 lifecycle E2E 保留 Session/Input/Run 来源、通道、正式消息归属，以及拒绝旧 evaluation 字段后没有新 Input 的 PostgreSQL 回读 |
| test_agent_async_e2e.py 的重复生命周期与旧字段断言 | 更名为 test_real_provider_e2e.py，manual workflow 与 gate 同步更名；只保留真实供应商经 API/worker/SSE 到达同一 Run 结果的独立探针，删除失效的 run.input_id SQL 与单 input_id 响应断言 |
| 三份相同的 PostgreSQL 连接池 fixture、chat router 内重复 DSN helper | 既有 integration/conftest.py 的 postgres_sessions 与 support/postgres.py；连接池仍按函数和同一事件循环创建、关闭，各用例继续拥有自己的数据与清理 |
| checkpoint 测试中的 Context/prompt 样板、旧签名 TypeError 墓碑 | Context 用例归 test_context_auth.py，保留真实工作区文件和两种 prompt 结果；删除重复装配案例、空壳 import helper，以及只验证 Python 必需参数绑定的用例 |

资源清理只认当前生成器发布的统一标题、显式 `_yuxi_test` metadata 和统一 Receipt 前缀；删除历史标题正则、单独 `_yuxi_e2e` marker、旧回执前缀和按 Agent 名称猜测 Thread 归属的路径。Agent 清理保留当前测试实际生成的精确前缀及创建者约束。无标记的历史数据不再自动认领；负向案例要求旧标记不能授权删除。

`get_user_data_dir()/thread_id` 已没有生产者，删除其目录解析、删除函数、E2E 调用和人工旧目录 fixture。文件删除由当前 Project Workdir 清理拥有；保留真实 UserWorkspace 符号链接负控、路径边界、幂等与 PostgreSQL 并发和提交后失败验证。

部署配置用例保留宿主与 CI 入口。测试脚本的 readiness 验收直接执行 shell，仅替换 Docker 进程边界，覆盖默认地址、显式槽位地址和未就绪时不执行 pytest，删除写死命令字符串的断言。

## 替代方案

- keep：保留多份 item、工具正文与重复收尾，需要额外同步和对账，拒绝。
- narrow：只移动页面代码，保留 API 与提交模块两处回执恢复，未减少责任 Owner，拒绝。
- replace：新增独立测试生命周期管理器，与现有 Compose/CI 同时维护资源，撤下。
- remove：在现有状态、持久化和编排 Owner 中删除被接管的实现，采用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 每 Thread 一份 item，完整输入只有一个接收恢复 Owner | 流与历史覆盖、重复提交、迟到快照改写新 Run | sessionRuntime、sessionInput、useAgentInputQueue | 前端 unit、真实页面历史与输入重放、API/worker E2E | 分页与增量交错、同键冻结重试、保留新草稿、监视者启动后不再读取旧快照 | Passed |
| 工具只有一份持久结果 | 工具正文双写、引用来源读取旧字段 | tool_audit、Message 约束、tool_results | PostgreSQL/HTTP、工具及审批 E2E | 非空工具 content 插入被约束拒绝；跨 Run 与失败工具不能泄漏证据 | Passed |
| Run 终态提交先于资源清理与通知 | 过期 Owner 结算、取消丢失增量 | runner、Run repository | runner unit、真实 lease、取消与协作 E2E | 实际 worker 入口的已提交完成/等待和未提交失败只清理一次，取消、清理失败及 lease 负控 | Passed |
| 统计保留原口径并只执行一次聚合 | 日界与七日边缘误计 | dashboard repository | 独立边界值 oracle、真实 SQL 次数及 HTTP | 正好一日/七日、前后微秒与空桶 | Passed |
| 测试入口与 fixture 完成替代 | 新旧 CI 重复执行、遗漏恢复和附件用例 | run_tests.sh、E2E conftest、workflow | verifier 及其负控、完整套件 | 删除原 CI 用例或断开 selector 后 gate 拒绝；源码无独立测试运行器 | Passed |

### 执行证据

业务重构阶段的全量链路证据保留如下；测试资产删除与合并后的复验单独列出。

- 隔离环境内以 `python -m pytest test/integration/api` 执行 HTTP 批次：361 passed、1 skipped；其余 integration 排除 API 与三阶段 worker 拓扑文件：439 passed、5 skipped。六项跳过均为真实模型或外部连接探针，不计入通过数。
- 隔离环境内以 `python -m pytest` 执行 `run_tests.sh` 的同一组八文件确定性 E2E：39 passed；最新 runner 的失败与取消链路另复验 2 passed。API、worker、SSE 与 PostgreSQL 共同装配，最终状态和产物由测试回读。
- `test_background_job_worker_path.py` 按既有 CI 的停止 worker、准备、启动 worker、恢复与失败回调三阶段执行：3 passed。通用 integration 不重复选择这个具有拓扑前置条件的文件。

测试资产收敛后的最终复验：

- `docker compose exec -T api uv run --group test pytest test/unit -m "not slow" -p no:cacheprovider`：2652 passed、61 skipped、7 subtests passed。容器缺少仓库根文件而跳过的配置用例由宿主补跑；`uv run --project backend --no-sync --group test pytest backend/test/unit/config -q -p no:cacheprovider`：103 passed，未将重叠用例相加。
- `pnpm -C frontend test:unit`：621 passed；`lint:check` 与 `build` 通过。
- 新鲜隔离 API/worker/PostgreSQL/Redis 中，`python -m pytest test/integration/services/test_agent_run_lease.py test/integration/services/test_live_api_cleanup_run_rows.py`：21 passed；`python -m pytest test/integration/api/test_agent_create_resources.py test/integration/api/test_chat_router.py`：41 passed。
- 同一隔离环境执行 `python -m pytest test/e2e/test_agent_lifecycle_e2e.py::test_public_session_initial_text_stream_and_saved_items`：3 passed，包含迁入的来源归属和拒绝请求无新增事实断言。`pytest test/e2e --collect-only`：69 tests collected，仅证明所有现行入口可收集。
- 真实页面执行 `sessionHistoryLoading.js`，核对 950 条历史分页、滚动锚点、失败重试、窄屏、同键重试只接入一个 Run 并保留新草稿，以及两种输入法回车均不发送。`actionDropdownGrowth.js` 读取真实 DOM 与键盘事件，确认弹层高度、搜索结果和 Escape 的默认行为与冒泡均符合断言。
- `python3 scripts/verify_engineering_contracts.py`、其 66 项 unittest、文档构建、相对链接检查与 `git diff --check` 通过。独立 Reviewer 核对完整需求、diff、替代关系与测试 oracle，无未闭合阻断。

真实外部模型与服务的 `e2e-all`、更名后的真实供应商探针，以及完整 Cube 容器重建恢复脚本为 Not run；确定性 worker 恢复与取消证据不替代这些外部环境探针。

旧能力不存在：历史 item 副本、旧提交入口、工具终态 content 参数、独立测试运行器和重复 CI 用例步骤已删除；旧源码符号搜索与调用方复核共同证明替代完成。

重新引入条件：出现当前消费者、独立语义责任和可验证边界，经单独决策引入。

## 后果

跨异步请求、持久化与外部进程的时序必须由相应层级测试证明；必要的公开快照、执行恢复状态与表现层临时状态继续保留其独立职责。Schema 不兼容变更遵循现有空库基线与版本拒绝契约，不改写现有用户数据。
