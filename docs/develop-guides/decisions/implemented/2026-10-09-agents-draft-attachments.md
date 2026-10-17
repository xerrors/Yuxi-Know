# Draft 文件与消息附件提交

状态：implemented
类型：feature
Owner：backend/yuxi/modules/agents/services/attachments.py

## 问题

附件添加动作提前创建 Session 并写入 Workdir，用户尚未发送的文件已经可以被 Agent 读取。整个 Session 的附件被加入当前模型输入，后续排队附件也提前出现。Public 还要求调用方选择 OCR 引擎和解析对象路径，图片调用方把 PNG 标记为 JPEG。

## 决策

### 实现方案

上传为草稿、发送时绑定输入和写入 Workdir、私有 OCR 与共享文件语义继续生效。附件事实 Owner、行锁、准备/派发编排与来源清理由[事实归一决定](2026-10-09-agents-owner-simplification.md)拥有，替代本决定的 manifest、Input payload 准备字段和 Session/Message 附件副本。公开参数、限制与示例由[Public API](../../../advanced/agents-public-api.md#图片与文件附件)维护。

执行服务仅把本次 Input 与此前已消费 Input 的附件列入模型上下文。真实 Workdir 继续共享，相同 Project 的运行可通过文件工具发现后来提交的文件；Input 关联不构成文件隔离。取消排队不自动删除正式文件。Web、CLI、Demo 直接发送文件 id 与完整图片 data URL；Web 在首次 Input 接收成功后才进入会话路由，接收拒绝保留 composer 的文字、图片和 draft。

## 替代方案

保留 confirm 会使添加动作提前落盘，违反发送前隔离。文件写入后才提交唯一数据库事务会在崩溃后丢失准备归属。附件准备复用现有恢复循环，附件关系表只拥有文件事实，不引入通用任务平台。延迟到 Input 消费时才落盘会改变发送完成后的共享文件语义。为首次失败新增独立全局草稿状态可以跨页面迁移，但延后路由切换即可保留现有 composer，当前不增加这一状态层。

## 后果

数据库和文件系统不共享事务，接收与就绪之间存在明确的准备窗口；文件写入失败不会伪装为可执行输入。草稿是一次消息提交资源，另一 Input 需要重新上传，正式文件继续由 Workdir 操作。就绪提交后清理临时来源，正式内容由 Workdir 拥有；过期 draft 由附件行状态选择清理，来源不再作为永久备份。未完成准备会阻塞 FIFO，Input 错误可观察，恢复持续重试，操作人员仍需修复不可用的文件系统。共享目录允许运行中的工具看到后续输入的文件，模型上下文过滤不承诺物理隔离。

## 验证

以下记录本决定的原始验收；当前附件事实与恢复实现的验收见事实归一决定。在开发 Compose 的真实 PostgreSQL、Redis、MinIO、API 与 worker 上执行。确定性模型 oracle 检查实际模型请求，返回完成后重新读取目标 Turn、result Run、公开 Items 和文件；不使用官方 SDK 是否结束调用作为成功条件。

| 行为 | 证据 | 结果 |
| --- | --- | --- |
| draft 上传不创建会话或 Workdir，真实字节及用户/APP 隔离 | `test_public_agent_files.py`、`test_upload_boundary.py` 与 PG `test_input_attachments.py`；回读对象、PG、文件 | Passed |
| 幂等首次提交、文件失败、准备后崩溃、取消及会话归档/Project 软删除后恢复、并发唯一归属 | PG 故障注入后读取 Input/Receipt/Message/Run 及稳定目标字节；未就绪 consume 负向断言 | Passed |
| ready steer 到期后追加、B 失败保留 A 的修改及解析资源 | 同一真实 PG/MinIO/Workdir 测试回读旧原件、Markdown、图片、正式引用及重试结果 | Passed |
| 后续排队/取消附件不进入当前模型输入，文件继续共享 | worker E2E 的独立模型 oracle 拒绝 future.txt；取消后回读原件，第二 Session 读取同 Project 文件 | Passed |
| Public 私有辅助入口不可达、所有 Key 私有调用拒绝、PNG 类型正确 | HTTP 4 项边界、直接内容块 unit、worker PNG oracle、Demo 浏览器协议 | Passed |
| 私有预解析保留完整目录、OCR 默认配置仍生效、运行环境重建后附件可读 | 确定性 MinerU HTTP replay、真实解析/Workdir/资源字节及 runtime recreation E2E | Passed |
| Web 首次接收拒绝后保持 draft 与文字，重试保留同一附件 id | 真实 Web + API 上传/创建，浏览器拦截 events 返回 422；两次提交与 DOM/未提交资源/零正式引用回读 | Passed |

执行命令和回归数据：

```bash
# worker E2E 需要另一个终端运行确定性模型 oracle。
docker compose exec -T api uv run --no-sync --group test python -m test.support.openai_replay_server --port 8765

# 容器已有测试环境；普通 uv run 因镜像中的只读 yuxi.egg-info 无法同步，使用 --no-sync 执行同一环境。
docker compose exec -T api uv run --no-sync --group test pytest test/unit -m 'not slow'
docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_input_attachments.py test/integration/api/test_public_agent_auth.py -q
docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_thread_priority_inputs.py test/integration/api/test_public_agent_files.py test/integration/api/test_upload_boundary.py::test_attachment_upload_preserves_metadata_and_minio_bytes -q
docker compose exec -T api uv run --no-sync --group test pytest test/e2e/test_draft_attachments_e2e.py test/e2e/test_agent_lifecycle_e2e.py::test_attachment_survives_run_runtime_recreation test/e2e/test_document_parsing_artifacts_e2e.py test/e2e/test_ocr_config_center_e2e.py -q
docker compose exec -T api uv run --no-sync --group test pytest test/e2e/test_read_file_multimodal_e2e.py -q
```

后端 unit **2569 passed / 55 skipped**；PG/auth **14 passed**，FIFO/私有边界/上传回归 **17 passed**，HTTP 图片/上传原件及 artifact **3 passed**，最终公开契约/附件 unit/HTTP **29 passed**（新增 cancelled preparing 删除 guard 的负向案例由最终 unit 重跑覆盖）。实际 worker/解析 E2E **5 passed**。

Web lint、全量 unit **515 passed**、发送专项 **8 passed**、类型检查及 build 通过；CLI typecheck、**11 passed** 与 pack dry-run 通过；Demo lint、**13 passed**、build 和浏览器 **16 passed**。真实 Web 的上传与拒绝重试截图保存在开发机临时目录，不提交截图、Token 或运行数据。工程信任检查、检查器 **64 tests**、文档 build 与 diff check 通过，独立 Reviewer 已检查功能与证据边界。三端没有 confirm 调用或 JPEG/base64 旧形状包装。

外部 `E2E_VISION_MODEL` / `E2E_NON_VISION_MODEL` 未配置，read_file 真实模型探针 **2 skipped**；不能据此宣称外部视觉能力、非视觉模型拒绝后的 OCR fallback 或所有外部 OCR 服务已校准。MinerU replay 证明资源协议，真实 OCR 默认配置场景证明现有私有解析链路。当前查询/断线恢复已完成，见[查询恢复决定](2026-10-09-agents-query-recovery.md)；官方 SDK 完整调用的当前边界见[公开 API 参考](../../../advanced/agents-public-api.md)。
