# 收敛知识文档作业与投影清理职责

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/knowledge/services/background_jobs.py

## 问题

文档指定文件与 pending 两路重复实现参数更新、执行动作及 attempt 身份透传；ingest 借助跨阶段反复改写的文件元数据筛选索引项。定时投影清理使用自己的 outbox 事务，混在持久作业 Handler 中。异常日志使用不适用于 Loguru 的格式占位符。

## 决策

### 实现方案

文档作业保留持久 payload、Handler 名称与版本、两种遍历方式、进度和结果协议；一个私有执行函数收敛有参更新后 parse/index 的单文件操作，外层循环继续拥有取消、异常聚合和统计。ingest 显式保存登记成功项与解析成功的待索引项，仍按全部登记、全部解析、全部索引执行，并按输入位置形成最终结果。阶段内参数更新规则保持。

投影清理原样迁入 knowledge services 的 projection_cleanup，由 worker 的原 cron 注册；不接入 BackgroundJobContext，不修改事务提交、行锁、投影锁、失败重试和清理顺序。原入口直接移除，图谱 Handler 不搬动。日志使用 Loguru 占位符，记录任务、资源标识与异常类型，不输出上传路径或底层异常秘密。

## 替代方案

- 统一批量迭代框架：指定文件固定顺序，pending 使用 keyset 分页、动态计数及有界样本；合并会引入额外策略和状态。
- 逐文件完成 ingest 全流程：改变现有全局阶段顺序，不采用。
- 保留旧投影入口作为转发：所有 consumer 均在仓库内，直接更新注册与测试即可。

## 后果

指定文件与 pending 保留各自循环、分页、进度分母和失败统计；单文件参数更新及 attempt 身份只有一个执行实现。ingest 使用成功阶段集合，仍保留全部登记、全部解析、全部索引的顺序及原输入位置。索引前空参数更新与解析前无额外参数更新保持。

定时投影清理独立于持久作业 Handler，worker 使用原函数名与 cron 时序注册；旧入口不保留转发。图谱 Handler、文件失败 hook 和摘要投影规则保持。日志不再输出字面占位符，仅记录资源和任务标识及异常类型，持久结果与异常收尾协议不变。

## 验证

- Passed：宿主相关 unit 113 项，包含新增 40 项；覆盖参数原值与 owner 透传、参数更新失败跳过动作且继续后续项、动作与安全点取消传播、ingest 三阶段与原输入顺序、502 项跨页及样本外失败统计、真实 Loguru sink 与启停 cron 注册。独立验证另从仓库根运行相关 106 项，新增五项参数失败案例再经全量套件验证。
- Passed：同一组 31 项行为断言对修改前 Handler 全部通过；7 项日志测试对修改前实现均因缺少任务标识失败，对最终实现通过，区分等价整理和日志缺陷修复。该临时负控仅替换被测 Handler，不修改正式源码或 expected output。
- Passed：`docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_knowledge_projection_integrity.py -q`，13 passed；真实 PostgreSQL 回读 pending/applied、Chunk 与删除状态，验证失败重放、SKIP LOCKED 及等待晚到写入的投影锁。
- Passed：`test/e2e/test_milvus_text_retrieval_e2e.py` 两项分别通过真实 API/worker。既有检索删除场景回读 PostgreSQL、MinIO、Milvus 与 Neo4j；新增 ingest 场景读取两份不同文档，按结果位置回读 PostgreSQL 文件名/状态与解析正文。CI 按整文件选择，包含新增场景。
- Passed：`docker compose exec -T api uv run --no-sync --group test pytest test/unit -m "not slow" -q`，3191 passed、117 skipped。容器缺少仓库根目录等既有 skip 不能解释为已覆盖；部署配置未在此调整中变更。
- Passed：工程信任检查与检查器 unittest 66 项，源 Ruff check/format/import，新增测试 lint/format，文档相对链接与 build，`git diff HEAD --check`。
- Passed：独立 Review 核对实现、调用方、旧 Owner、测试和直接运行日志；投影清理、图谱 Handler、失败 hook、摘要函数的 AST 与修改前一致。

旧能力不存在：指定文件和 pending 不再各自实现单文件动作；ingest 不再改写并重读 file_meta 来选择索引项；旧 background_jobs 模块不再定义或转发投影清理函数。

重新引入条件：出现无法由现有两个循环表达的新调度 consumer 时重新评估；任何并行或阶段顺序改变必须独立论证并提供实际链路证据。

未验证范围：不包含真实外部模型、生产吞吐压测、进程崩溃故障注入或额外的停启拓扑测试；worker 启停配置只验证该迁移相关的冷启动 cron 注册。ingest 的自动索引阶段由 unit 断言，真实索引与投影清理由既有 worker E2E 验证。
