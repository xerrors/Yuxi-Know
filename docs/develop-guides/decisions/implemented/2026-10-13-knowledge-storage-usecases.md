# 知识存储装配与业务链路收敛

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/knowledge/manager.py

## 问题

知识检索与图谱需要相同的 Milvus 公共字段、索引和 embedding 装配；独立维护允许单侧漂移。同步客户端查询的取消必须保留实际运行线程的容量，客户端初始化需要跨请求复用。删除与评估筛选的查询量需要受操作范围约束，文件状态与检索默认值需要一致的读取语义。

## 决策

### 实现方案

`knowledge/storage/milvus.py` 拥有公共正文、向量字段、BM25 函数、索引和模型编码装配，各实现提供自己的列顺序和业务字段。`storage/offload.py` 按事件循环维护 Milvus、Neo4j 各 8 个查询预算；取消等待后，线程实际完成才归还容量。Milvus 执行器持有 `KnowledgeGraphService`，首次构造在线程内赋值缓存；初始化取消先等线程落定再释放初始化锁。图服务复用基础设施 Neo4j 连接，负责 PG 事实和两类图投影。

`KnowledgeBaseRepository.mark_deleted` 在一个事务内写入 KB/文件 tombstone，通过 UPDATE 与 INSERT SELECT 批量登记幂等 outbox。外部清理完成后 `purge` 物理删除；有效名称预检使用 EXISTS，最终冲突仍由 D3 唯一索引拒绝。评估 repository 在 BackgroundJob 提供的事务中完成成功/失败写入，service 保留 registry 所需的导出；筛选分页在 SQL 中执行。

`KnowledgeExecutor` 区分类型执行器与配置 ORM，共用 PG/MinIO 文件行为。`IngestionChunk` 拥有分块到索引的内部形状，Milvus 主键与 chunk_id 列使用同一 ID。PG 记录、向量列数组、检索 metadata、虚拟目录与公开文件列表保留明确转换和真实消费者。`file_status.py` 统一当前状态与历史读取别名；模型 JSON 归一化统一实体属性合并、别名和关系去重，payload 只转换局部 ID。

`chunking/dispatcher.py` 与 `presets.py` 拥有应用分块契约。ragflow_like 是本地修改的适配实现，依赖 source_spans 保证原文定位；不能当作未修改 vendor 替换。语义分块显式接收 embed_model_id，索引入口按现有规则补入系统 embedding spec，模型故障使索引失败。检索配置按 dataclass 默认值、存储选项、请求参数依次叠加，面板与运行时共享缺省阈值 0.0 和 BM25 数量 50；已有显式选项保持有效。

## 替代方案

各实现继续独立装配会保留数据契约漂移；把全部用例收进 Manager 会扩大其外部客户端职责。当前 Manager 的类型路由和文件操作入口有路由、worker、Agent 工具消费者，保留这些入口可避免重复装配。graph_utils 只承载纯转换、标识和 Cypher 模板，保留图域归属。

统一为一种文件响应会改变虚拟目录与公开接口；因此只统一内部摄取形状和共用文件行为。列表使用持久统计以避免逐库聚合，详情和文件页实时聚合；两条交付路径由同一个 query_kb_file_stats 定义字段，成功、失败及 lease 收敛在事务内刷新持久投影，保留 D4。共享授权校验的跨域依赖保留最终授权职责，在结构审计 Step 9 复核。

## 后果

外部 HTTP、存量 PG 数据和 Milvus 列顺序保持兼容。新图集合启用公共正文匹配参数，已有集合和用户配置不自动重建或迁移。缺省检索行为与面板一致；错误的语义分块配置显式失败。知识库批量删除仍是原子事务，目标 KB 的所有文件写锁保持到提交，其他 KB 文件不参与锁定。

## 验证

| 验收主张 | 直接证据 | 结果 |
|---|---|---|
| 公共 schema 与索引一致 | storage_contracts 从文档、实体、三元组三个入口断言固定字段/索引；独立进程恢复单侧 enable_match=False 后失败 | Passed |
| 并发预算和客户端生命周期 | 真实阻塞线程取消测试；40 个并发客户端请求只构造一次；取消首请求后客户端仍复用，恢复旧实现后检测到两个构造 | Passed |
| 删除及筛选按请求范围执行 | 1,200 文件真实 PG 删除不超过 6 条语句，outbox 回读 1,201 条；其他 KB 行锁不阻塞；205 条评估结果在 SQL 筛选后分页 | Passed |
| 统计、来源和失败收敛 | projection_integrity、stats_refresh、query_scale、audit_persistence 合计 35 项真实 PG/Redis 与 HTTP 测试 | Passed |
| 摄取、检索和图谱最终状态 | Milvus E2E 真实 HTTP/worker/PG/MinIO/Milvus/Neo4j，三检索模式、公开来源、重复实体/关系、重建、软删和失败恢复均回读存储 | Passed |
| 分块与默认配置 | 固定输入来源行范围 17 项；语义模型缺失/不可用负例；缺省 0.0/50 与显式保存值覆盖测试 | Passed |

补充 `test_background_job_repository.py`、`test_chunk_config_boundary.py`、`test_milvus_graph_delete.py` 共 41 项通过，覆盖钩子同事务、真实 TCP 配置拒绝及 Neo4j 共享实体删除回读；集成测试合计 76 项通过。Neo4j 测试使用与当前代次契约一致的 chunk_id，并仅清理自身唯一标签。

完整 non-slow unit 为 **2747 passed / 60 skipped**，独立 Reviewer 复验相关 53 项并核对最终 E2E 与负向实验。

实际命令：`docker compose exec -T api uv run --group test pytest test/unit -m "not slow"`；集成测试选择 `test/integration/services/test_knowledge_{projection_integrity,stats_refresh,query_scale,audit_persistence}.py`；E2E 选择 `test/e2e/test_milvus_text_retrieval_e2e.py -m e2e`。工程契约检查及其 unittest、Ruff、文档构建和 diff 检查随提交执行。

E2E 的既有全局清理遇到共享 Workdir 重叠保护，本次通过仅允许这一指定测试运行的临时 pytest 插件关闭全局清理；测试自身 finally 清理唯一 KB/provider。没有删除重叠资源或弱化生产保护。外部模型质量不在验收范围：E2E embedding 使用固定 TCP 协议 fixture，图输入使用固定抽取结果；模型客户端复用在并发单测验证。容器内 60 项根目录工程文件相关单测按既有条件跳过，宿主机单独运行工程 gate。

旧能力不存在：生产路径不再包含两份 Milvus 公共装配、有界卸载副本、名称全表扫描、评估筛选扫描、文件仓储中的 KB 删除用例、空的分块默认函数或每分块模型重建。

重新引入条件：存在不同持久化协议、独立生命周期或不兼容公开消费者，并以独立证据证明共享实现无法表达时重新评估。
