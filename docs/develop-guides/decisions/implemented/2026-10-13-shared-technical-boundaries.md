# 共享技术依赖与结构审计收尾

状态：implemented
类型：simplification
Owner：backend/yuxi/infrastructure/redis/queue.py

## 问题

业务域反向引用 worker 健康入口、Agent 队列访问器及 bootstrap 注册表。配置定义、注册汇总和存储同处一个文件形成真实导入环；模型适配器改写异常类型。剩余审计条目需要按当前消费者区分共同机制与域策略。

## 决策

健康键、TTL 与续租写入归 infrastructure/worker_health；ARQ 连接生命周期归 infrastructure/redis/queue，Agent Run 与 BackgroundJob 各自拥有投递策略。池的初始化串行化，失败允许后续重试。关闭 ARQ 出错时仍清理共用 Redis；API 与 worker 的关闭边界记录组件失败并继续后续清理，worker 返回后由 ARQ 关闭自己的消费池。JobDefinition 与惰性字符串表均归 background_jobs/registry，保留持久 job_type/version 和 handler 契约。

Option 是携带读取行为的配置对象，由 system/services/options 拥有，沿用各域 `.get()` 消费入口。配置服务拥有校验、管理员提交/回滚、提交后缓存失效和表单输出；repositories/options 拥有 SQL；bootstrap/options 显式汇总并同步域定义。运行时读取不反向导入 documents/extensions 定义，两个汇总文件环消失。system/options 保留系统定义及显式汇总入口，DashboardService 归 services。共享授权查询归 identity/repositories/resource_grants，保留当前角色校验与锁。

文本模型适配器重新抛出原异常，load_chat_model 与 select_model 分别服务完整 LangChain runtime 和文本任务。模型供应商的 credentials 叶子契约供缓存重建与服务共用；models/providers/service 拥有 DeepSeek OCR 当前支持的供应商凭据及端点解析，documents 只消费结果。

Workspace 拥有 runtime 路径映射及 Project 领域异常，Viewer 不再导入 Agent runtime。知识下载直接调用元数据读取，删除纯别名和无效 refresh 参数。PREPROCESSED_UPLOADS_KEY 由知识上传元数据边界拥有，前端及持久 Job 的既有 `_preprocessed_map` 字节保持有效，单文件处理参数继续过滤此键。

## 替代方案

统一所有缓存会混淆模型快照 fail-closed、Option 非敏感值故障回源/版本 CAS，以及知识配置读取回源但锁/失效失败阻止修改的责任。共用 Redis 客户端已经在基础设施，剩余容错保留域策略，不添加泛型吞错包装。

同步与异步 embedding 已共享 payload、响应解析、重试预算和延迟；独立传输保留同步 Milvus 检索线程与可取消异步 IO 的 consumer，以及 requests/httpx 的既有异常契约。强行统一会引入事件循环桥接或额外线程。

DashboardService 保留 HTTP 用例入口和会话详情组装，报表 SQL 直接读取跨域 ORM，移除跨域 AgentRepository 构造。models 保留文档化 Python 扩展入口和 tables.py 命名；namespace package 保持有效导入，不为目录外观补空文件。Project 归档继续查询锁定 Agent 事实并拒绝未完成工作，Workdir 授权服务读取 Session，保留真实用例依赖。

## 后果

HTTP、存量数据、任务类型、Redis 键、锁值与前端上传协议保持兼容。配置写入只有 service 一个提交点。模型异常恢复原类型，调用方能按供应商故障类型诊断。mark_for_improvement 已使用 builtin 分类，disabled_mcp_tools 已表达禁用集合；这些已有事实在审计中明确标注。

配置与 checkpoint 锁具名化但保持旧值；其他既有散列键保持算法与作用域以兼容滚动部署。新锁键使用 owning 域前缀，事务锁随事务结束释放，session 锁由同一物理连接释放。不另建可漂移的锁注册表，也不因统一命名迁移现有键。API 分页限制、知识上传 100 MiB、Agent 附件 5 MiB 均由实际输入/用例边界拥有，公开 limits 从附件服务生成。

## 验证

| 验收主张 | 直接证据 | 结果 |
|---|---|---|
| 配置 HTTP 写入归 owning transaction | 独立 PG 回读值、非法负数拒绝、密钥脱敏、提交失败回滚 | Passed |
| 配置缓存失败与恢复 | 真实 Redis TCP 拒绝后 PG 回源、恢复后回填、敏感值不缓存、旧版本 CAS 拒绝 | Passed |
| 原有锁与配置同步互斥 | 独立 PG 连接持有旧字面值 94721801，同步等待后完成 | Passed |
| 模型传输与异常保持 | 同步/异步真实 TCP 固定请求和响应、429 重试、400 与恢复；异常类型及身份断言 | Passed |
| Worker 健康与域边界 | 真实 Redis TTL 失效/无界租约拒绝；Project 未完成工作拒绝后归档；Dashboard HTTP 统计及明细 | Passed |
| ARQ 初始化与关闭 | 并发消费者持有同一池、失败重试；真实 ARQ Worker.close 在组件关闭失败后仍释放消费池 | Passed |
| Shipping 启动、注册及投递 | API/worker 重启，liveness/readiness、215 个 OpenAPI 路径中的知识/图谱/评估能力、六类 Handler 与 hooks 加载；真实 worker 知识 E2E | Passed |
| 目标倒置与循环消失 | AST 检查 391 个模块，指定配置及模型路径无反向可达边，repositories 无 services 导入；旧符号搜索包含文档、测试、注册字符串 | Passed |

实际命令与结果：

- `docker compose exec -T api uv run --group test pytest test/unit -m "not slow" -q`：**2750 passed / 60 skipped**。
- `docker compose exec -T api uv run --group test pytest test/integration/services/test_shared_technical_boundaries.py test/integration/services/test_optional_dependency_failures.py test/integration/services/test_worker_health_redis.py test/integration/services/test_project_thread_archive.py -q`：**20 passed**。
- `docker compose exec -T -e PYTHONPATH=/tmp:/app api uv run --group test pytest -p step8_cleanup test/e2e/test_milvus_text_retrieval_e2e.py -m e2e -q`：**1 passed**。真实 HTTP/worker/PG/Redis/MinIO/Milvus/Neo4j 回读摄取、三种检索、来源、图谱、重建、软删与恢复事实。
- 独立测试进程恢复无锁池初始化后，十二个消费者创建十二个池，同一客户端断言失败；恢复 `raise Exception` 包装后，原始 ConnectError 断言失败。候选生产文件保持不变。
- 工程契约 gate、64 项工程 unittest、变更 Python Ruff/format、相对链接、文档构建与 diff 检查随提交执行；全新独立 Reviewer 核对完整需求、源码、diff 和证据。

E2E 沿用仅允许指定测试运行的临时插件关闭共享环境全局清理；该测试在 finally 清理自己的唯一 KB/provider，保持既有 Workdir 重叠保护。worker 健康测试的唯一键有自己的 finally 清理，显式声明 self_managed_resources。容器内 60 项根目录工程文件相关 unit 按既有条件跳过，宿主机另跑工程 gate。外部供应商模型质量、Kubernetes 与生产部署未验证；TCP fixture 和固定图输入只证明协议与存储链路。

旧能力不存在：业务运行时不再导入 worker 健康入口、Agent ARQ 池或 bootstrap 任务表；配置读取不再反向导入各域定义；知识仓储不再反向依赖身份 service；模型缓存不再依赖 provider service；纯元数据别名、无效 refresh 与异常改型包装不存在。

重新引入条件：出现新的真实消费者，且独立证据证明现有边界无法承载其生命周期或协议。
