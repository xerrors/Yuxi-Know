# Agents 状态与附件事实归一

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/services/attachments.py

## 问题

附件归属和准备状态由对象 manifest 与多个 JSON 共同表达，提交与恢复重复编排文件准备和派发。Session 读取经过旧 Thread 字典再次转换；配置同一时点重复存储，公开状态要求调用方纠正协作等待。这些重复来源使权限、重试和结果恢复难以保持一致。

## 决策

### 实现方案

附件 ORM 与 repository 拥有用户/APP、文件信息、Input 归属、准备状态和存储位置。上传只建立 draft；接收事务锁定附件行并绑定 Input，消费事务再绑定该 Input 的最后一条正式 Message。统一准备函数将已绑定文件写入 Workdir、提交就绪事实并清理临时内容；现有恢复循环调用同一函数。调度器只领取附件全部就绪的输入，回执读取没有准备、派发或文件副作用。Message 通过附件的 message_id 批量读取展示信息，Session 不保存附件副本。输入与附件关联由[输入投影分离决定](2026-10-10-input-message-projection.md)和[提交级附件简化](2026-10-10-input-attachment-simplification.md)更新；Receipt 不再拥有附件归属。

Session repository 批量读取当前 Turn、Run、输入数量、已读标记和活动时间；单一资源投影直接生成 HTTP/SSE 使用的 Session。列表、搜索、详情和更新后的读取复用该投影，搜索仅附加命中片段。删除旧 Thread 响应拼装与时间字符串往返转换。

Session 默认配置、Input 接收快照和 Run 执行快照分别表达不同时间点；每个时点只有完整快照。普通输入复制默认配置并应用显式覆盖；steer/resume 使用当前 Run 快照。执行拒绝缺失快照，避免逐层回退到最新 Agent。工作状态、waitpoint、未读标记分别拥有各自含义；协作等待公开为执行中，普通客户端直接消费公开工作状态。

本决定部分替换[机制对齐决定](2026-10-09-agents-api-mechanism-alignment.md)、[资源契约决定](2026-10-09-agents-resource-contract.md)及[配置及取消决定](2026-10-09-agents-session-lifecycle.md)的重复事实与状态策略，并替换[附件提交决定](2026-10-09-agents-draft-attachments.md)中的事实副本、锁与恢复编排，并取代[草稿对象扫描决定](../archived/2026-10-09-draft-cleanup-batches.md)。保持用户/APP 隔离、Input FIFO/steer、提交后派发、附件就绪边界和明确 result_run_id。不建立通用任务平台，不迁移历史附件 JSON，不加入旧协议兼容层，也不改变官方 SDK 完整调用的 P1 边界。

## 替代方案

保留现有 manifest 与 JSON 可避免新增表，但继续承担锁、反查和多副本恢复成本。仅缩小 JSON 副本仍缺少可锁定的附件事实。附件表替换隐含数据库，接受 Schema 的明确维护成本。Session 只增加转发层无法删除旧形状；选择直接资源投影。配置兼容若有明确历史数据承诺，应单独进行一次性转换。

## 验证

共享开发 PostgreSQL 反复进入恢复并中断登录和建表。实际链路验证使用 main 源码挂载的临时 PostgreSQL、Redis、API、worker 和 provisioner，复用 MinIO 与确定性模型 oracle；验证后清理测试资源及临时环境，不改动原环境业务数据。该结果不代表原共享数据库已恢复稳定。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 附件只在所属用户/APP/Input 中绑定一次 | 并发重复绑定或越权，JSON 归属漂移 | 附件模型与 repository | 真实 PG/HTTP 并发及文件回读 | 他人/其他 APP、过期 draft、重复占用、并发删除 | Passed |
| 单一准备函数恢复已绑定文件，调度只领取就绪输入 | 回执读取派发、未就绪执行或来源永久保留 | 附件 service、scheduler、恢复循环 | 真实 worker、崩溃重试及 Workdir/MinIO 回读 | 准备失败、提交后崩溃、重复准备 | Passed |
| 所有 Session 读取使用相同资源投影 | 列表/搜索与详情字段或状态不一致 | Session repository 与资源投影 | PG/HTTP 契约与搜索分页 | 不可见 Session、相邻 Run、搜索逐项快照 | Passed |
| 同一时点配置唯一并冻结 | Session/Agent 更新改变已接收执行 | 配置 snapshot、Input、Run | unit、PG、worker 配置冻结 | 缺失快照、修改默认配置、steer/resume | Passed |
| 三端直接消费公开工作状态及等待内容 | 协作等待误终止、未读被当成执行状态 | HTTP/SSE 投影与三端 | unit、真实 SSE/浏览器/CLI | 协作等待、人工等待、失败/取消与未读组合 | Passed |

旧能力不存在：对生产源码负向搜索 manifest、附件 JSON 归属反查、附件 advisory lock、旧 Thread 拼装、同层配置副本与协作等待状态修正，核对全部当前 consumer、测试及正式文档。

重新引入条件：存在明确且无法由当前附件表、配置时间快照或资源投影满足的 consumer，并由新的决定说明 Owner、证据和维护成本。

当前直接证据：真实 PG 附件、FIFO 与 Schema 升级 **22 passed**；真实 HTTP 文件、Session 及 Items **10 passed**；真实 worker 配置、附件和协作 **9 passed**。重新读取 Input/Receipt/附件行、Turn/result Run、公开 Items、Workdir 与 MinIO 字节及来源，验证就绪和结果归属。v5→v6 重复执行保留既有 Input，数据库拒绝无路径的 ready 行；文件绑定、准备失败、提交后崩溃、删除提交失败和未就绪消费均有负向案例。

```bash
docker exec yuxi-owner-api uv run --no-sync --group test pytest test/integration/services/test_input_attachments.py test/integration/services/test_thread_priority_inputs.py test/integration/services/test_agent_input_schema.py::test_attachment_schema_upgrade_is_idempotent_and_preserves_inputs -q
docker exec yuxi-owner-api uv run --no-sync --group test pytest test/integration/api/test_public_agent_files.py test/integration/api/test_public_session_resources.py test/integration/api/test_public_session_items.py -q
docker exec yuxi-owner-api uv run --no-sync --group test pytest test/e2e/test_session_config_e2e.py test/e2e/test_draft_attachments_e2e.py test/e2e/test_session_cooperation_e2e.py -q
```

提交前补齐原有 consumer：真实 PostgreSQL 协作专项 **55 passed**，HTTP 上传边界 **4 passed**，完整解析目录附件 E2E **1 passed**。完整生命周期集合覆盖 **16 个场景**：初次执行首项因临时模型重放服务未就绪而超时，其余 **15 passed**；服务就绪后重跑三个初始输入场景，**3 passed**。附件行、原件及解析资源、删除结果和 Input/Run 配置冻结均直接回读，断言不再消费 manifest 或同层配置副本。

三端单元及构建：后端 **2573 passed / 55 skipped**；Web **514 passed**，lint/build 通过；CLI **15 passed**，typecheck/pack dry-run 通过；Demo **13 passed**、浏览器 **18 passed**，lint/build 通过。真实 Web 运行 `frontend/test/browser/sessionPublicStatus.js`，回答两题和允许工具均由 `requires_action` 恢复到目标 Turn 完成，并检查 waitpoint、新 Run 与 result_run_id。Web、CLI、Demo 都注入已提交响应丢失和 SSE 失败，通过同一回执恢复而不重复 POST；Web 刷新、CLI 双页查询和 Demo 两轮结果、用户/APP 切换均回读目标结果及附件原件字节。截图只保留于本地测试输出。

独立、无开发上下文的 Reviewer 核对完整需求、diff、Owner 和证据，发现的搜索逐项查询、无调用方活动查询、人工恢复旧状态判断和文档漂移均已修复。浏览器检查通过真实控件恢复，配置 oracle 保留固定模型/审批值和实际模型请求校验。

工程契约检查、检查器 **64 tests**、相对链接与 docs build、Ruff 和 `git diff --check` 通过。容器复用已安装环境执行 `uv run --no-sync --group test`；普通 sync 会写入只读的 editable 包目录。

未验证范围：官方 SDK 完整调用继续属于 P1；未把确定性模型的协议验收视为外部视觉或 OCR 服务能力通过。历史附件 JSON 和缺失配置快照不在转换范围。

## 后果

附件表增加明确的 Schema 维护成本，并删除对象 manifest、JSON 归属反查、多处记录补写和文件 advisory lock。准备期间保留临时内容；就绪提交后删除来源，清理失败由现有恢复循环重试。跨存储不具有原子事务，持久准备状态和 ready 消费门禁拥有恢复边界。Workdir 修改不会被重复准备覆盖，草稿不承担正式内容的永久备份。

当前数据库基线由[初始 Schema 决定](2026-10-15-initial-schema-baseline.md)拥有，[app-init](2026-10-18-app-initialization.md) 执行初始化并拒绝不兼容版本；本记录中的 v5→v6 验证只保留为历史证据。不导入历史 JSON，不转换缺失快照。需要历史数据支持时单独进行一次性转换。Session 默认配置更新只影响后续普通输入，已接收配置与当前 Run 保持各自时间快照。协作等待继续执行，人工等待要求响应，未读标记单独展示。
