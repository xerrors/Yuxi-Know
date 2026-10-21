# 知识、会话与测试宿主的职责收敛

状态：implemented
类型：architecture
Owner：ARCHITECTURE.md

## 问题

知识原件暂存和图谱任务提交在 HTTP 路由中重复组织业务步骤；失败、取消与整树停止重复派生队列暂停。前端文件上传将并发、XHR 与渲染混放，运行状态初值又遗漏实际消费者需要的字段。重复编排与隐含契约使相同规则需要在多个入口维护。

上传的同步异常、主动取消和迟到回调还影响用户可见状态：同步失败通知早于受控文件列表刷新而被丢弃，取消显示失败提示，结束后的回调能覆盖清理或重传。SSR 测试宿主则启动不需要的客户端预构建，并在后期初始化失败时留下 watcher；缓存耗尽已造成[共享宿主磁盘事故](../../postmortems/2026-10-21-vite-test-cache-exhaustion.md)。

决定采用实际消费者需要的窄用例与明确资源边界。`ARCHITECTURE.md` 是边界导航入口，运行事实分别由下列服务、model、repository 和测试 helper 拥有；本记录不替代源码、机制文档或事故复盘。范围外的 [Run 终态](2026-10-21-run-terminal-lifecycle.md)与[准入准备](2026-10-21-run-admission-preparation.md)决定保持独立。

## 决策

### 实现方案

HTTP 入口校验权限、调用领域用例并投影响应；各用例保留自己的持久化和发布阶段。前端只提取文件上传的实际共享逻辑，测试宿主只管理自己创建的资源。

#### 知识原件暂存

`knowledge/services/uploads.py` 的 `stage_document` 消费安全取得的字节，依次计算哈希、查询现有未删除 PG 文件、写入 MinIO、查询同名文件。普通上传与工作区保留原 basename、毫秒时间戳和后缀的对象键、小写展示名；URL 保留 hash.html、HTML MIME、原始 URL 展示名与 final_url。没有 kb_id 时使用 unknown 前缀，Manager 的相关查询直接返回且不访问 PG。API 响应层复用普通上传和工作区的共同字段，各入口保留自己的成功包装与重复内容 409 文案。

路由校验管理员和知识库 manage 权限及能力门禁；HTTP 上传在请求期内限量消费流，URL fetcher 拥有白名单、SSRF、重定向和 10 MB 上限，Workspace filesystem 拥有 no-follow 和 100 MB 有界读取。后续添加、解析用例拥有正式文件、Job 登记、事务及提交后投递，延续[知识存储决定](2026-10-13-knowledge-storage-usecases.md)；当前流程由[知识库机制](../../../mechanisms/knowledge-base.md)说明。

#### 图谱提交

`knowledge/services/graph_build.py` 拥有 start、reconcile 与 reset 的请求准入和唯一 Job 登记。构建按活动 Job、知识库存在、配置锁定的次序判断；修复先验证 mode，再查活动 Job 与知识库。持久唯一登记继续裁决预检后的重复提交，提交后才投递。路由保留权限、响应和错误协议；worker 消费已有 action，直接调用拥有配置校验、构建和投影锁的 `KnowledgeGraphService`，不会再次提交自己。

#### 队列暂停与恢复

`agents/services/queue_control.py` 只在调用方已经锁定的 Thread 和事务中，按持久待办派生 queue_paused。取消待办仅在队列已暂停时刷新。Thread 锁、恢复意图、整树门禁、commit 和 dispatch 继续由各调用用例拥有。Input model 拥有恢复标记的 JSON 编码与 Python/SQL 表达，repository 拥有优先排序、附件阻挡、单独消费及恢复序号边界。

[停止与恢复决定](2026-10-17-agent-stop-and-queue-recovery.md)的 FIFO、steer、waiting、幂等重放和整树恢复范围保持。SQL 沿用原布尔 cast，不扩大为对历史异常 JSON 的严格布尔治理。完整协议见[输入队列与调度](../../../mechanisms/agent-request-queue.md)。

#### 会话运行状态

`useAgentThreadState` 创建 `runStateVersion: 0`、`cooperationWaiting: false` 和 `approvalSubmitting: false`。`sessionRuntime` 继续拥有每 Thread 的共享观察、恢复、历史与命令，流、队列和审批保持现有分工；清理后重新观察创建独立初值，版本递增与身份校验保持。

#### 浏览器文件上传

`useKnowledgeUploadQueue` 接收原文件列表与组件的格式判定函数，派生有效文件列表，拥有最多十个并发的文件/目录队列、XHR、UID 状态、进度、聚合与列表清理。`FileUploadModal` 使用现有 fileApi、认证头和目录模式装配，拥有过滤规则、表单、同名提示及正式提交。URL 抓取和个人空间提交时批量导入保持各自时序。

模式切换丢弃未开始任务并清空统计，已发出的 XHR 仍占并发槽位；失败释放槽位并继续 FIFO。`customRequest` 同步返回 Ant Upload 保存的 abort 句柄，主动删除调用原生 XHR 中止并静默结束等待。单请求闭包以 settled 标记阻止结束后的进度和终态回调，保留取消统计，避免改写列表清理或同 UID 重传。

同步准备和发送异常、缺少知识库 ID 在 Vue `nextTick` 后复用失败路径，使 Ant Upload 的受控文件列表完成刷新后接收错误；实际 XHR 异步事件直接通知。Promise 先结束再通知消费者，异步事件中的消费回调异常保持可观察，既定请求状态和后继发送不受影响。真正的网络、HTTP 和解析失败继续提示，用户可删除错误条目后重新上传。

#### 测试宿主

`frontend/test/helpers/createTestServer.js` 只服务 SSR 与静态资源测试，设置 `optimizeDeps: { noDiscovery: true, include: [] }` 关闭不需要的客户端 depsOptimizer，保留真实 Vite plugin、alias、SSR 与 PDF CMap HTTP；shipping Vite 配置不变。有真实客户端的 agent-demo 常驻入口和 Node HTTP fixture 不适用此缓存协议。

helper 通过早期 configureServer hook 保存已构造的 server。后续初始化失败时先等待 close，再在 finally 回收自己的 cacheDir；正常创建也包装 close，关闭抛错仍执行缓存回收。关闭和缓存清理成功时保留原初始化错误，两者自身失败时显式传播其错误。生命周期 unit 读取真实生产模块、optimizer 与 watcher 状态及目录；既有 PDF 用例独立证明 CMap HTTP 和构建字节。

## 替代方案

采用各真实消费者需要的窄边界，拒绝以下扩展：

| 替代方案 | 不采用的原因 |
|---|---|
| 保持路由、组件和暂停派生的重复实现 | 多个入口仍需分别维护业务次序，源码正则不能直接证明队列行为 |
| 来源插件、全摄取参数袋或 PG/MinIO/Job 通用事务 | 暂存和正式登记阶段不同；统一会改变来源读取、提交和补偿边界 |
| HTTP 与 worker 共用图谱提交准入 | worker 自己就是活动 Job，会拒绝自身或递归提交 |
| 按方法数量拆分 Manager 的 Files/Retrieval/Admin 转发面 | 响应已消费 read model，executor 选择有真实消费者，缺少增加转发层的收益证据 |
| 通用 QueueController 或全面 ThreadSession 接口 | 调用用例仍拥有锁与事务，sessionRuntime 已提供共享观察和命令，全面替换扩大恢复链路 |
| 只提取 XHR、保留 async 请求句柄或只过滤取消提示 | 调度与聚合仍依赖组件；Promise 不满足 Ant 同步 abort 契约；伪失败、迟到回调和过早通知仍存在 |
| 通用上传状态机或统一三种来源 | 单请求 settled 已能裁决终态，URL 与个人空间的读取、提交时点无需改变 |
| 仅增加 rm 重试、共享缓存、假 Vite 或修改 shipping 配置 | 没有关闭多余后台写入，或引入跨测试状态、丢失真实 SSR 证据、改变产品开发环境 |

删除权限、来源安全、去重、任务唯一性、附件等待或恢复优先会破坏公开承诺；删除显式添加阶段、自动删除共享 hash 原件也会改变持久行为。

## 后果

原件暂存成功只证明对象和预处理信息可用。去重只读取已有未删除文件，不排除未登记对象或批内相同内容；失败保留已上传对象及批次前序结果，URL hash 对象可以共享。此边界不提供跨存储原子提交或新的对象失败补偿。

图谱活动 Job 预检与 reset 仍存在原有跨请求竞态，不能据用例归属推断串行化。队列暂停的共同派生不取得锁、提交事务或改变恢复协议。Manager 与 sessionRuntime 继续提供现有能力，文件重新提交继续承担既有重试方式。

SSR hook 只能关闭已经取得的 server；configureServer 前未暴露资源的 Vite 内部故障不属于关闭保证。关闭或清理失败可能取代初始化错误，不增加多错误优先策略。未来需要客户端转换的测试须明确独立运行责任。

测试与生产仍共享宿主磁盘，缓存命名隔离不等于配额、文件系统隔离或部署监控。本地串行验证不构成跨 Agent 全局锁。事故影响、恢复、有限只读核验及其覆盖限制由[事故复盘](../../postmortems/2026-10-21-vite-test-cache-exhaustion.md)保存，健康和空集合查询不能证明生产业务完整性。

## 验证

### 合并前已执行的验证

以下 Passed 来自这些实现和修复提交时的执行记录，本次文档整理没有重跑产品测试。集合存在交集，计数不相加；最终完整集合为前端 770 项、后端 3080 项。

| 边界 | 直接证据与已执行结果 | 负向案例 |
|---|---|---|
| 原件暂存 | Passed：真实 TCP upload/workspace、ASGI URL 加真实 PG/MinIO 的 integration 经独立加并发上传复验 5 项；相关单测、fetcher/upload boundary 和真实文件系统检查通过 | 独立 SHA-256 与对象字节、大小写/unknown/MIME、未认证上传、PG 内容 409 且不新增对象、同名/tombstone、批内重复、无 kb_id 不访问 PG、真实 no-follow/限量读取 |
| 正式解析产物 | Passed：真实 worker artifact/delete E2E 1 项，回读 parsed PG、Markdown/图片字节与对象删除 | owner 丢失补偿、重试替换、单文档删除不误删其他对象 |
| 图谱请求 | Passed：真实 HTTP/PG 与正式 worker 5 项经独立复验；空知识库 build/reconcile 回读唯一 payload、attempt 1 和 success | 活动 Job/原配置保持，未锁配置、非法 mode、唯一登记冲突；空 chunk 不调用外部 LLM |
| 暂停与恢复 | Passed：真实 PG stop/priority 与 cooperation/lifecycle 合计 101 项，独立 stop/priority 复验 38 项；真实 worker 生命周期及协作 E2E 30 项、0 skip，389.33 秒 | 空/有待办、删除末条、不重暂停活动队列、旧 steer、附件未就绪、幂等重放、整树恢复范围 |
| 会话初值 | Passed：sessionRuntime 与完整前端 unit 验证初值、Thread 隔离、清理重建、共享观察和迟到恢复 | 逐个删除三个默认字段时精确断言失败 |
| 文件上传 | Passed：queue 23 项及 folder 3 项，共 26 项；真实受控 AUpload 覆盖 open/header/send 同步异常和缺少知识库 ID；消费回调抛错后既定终态与第 11 项 FIFO 发送保持 | 通知前删除、结束后 progress/error/abort、同 UID 重传、HTTP/网络/解析错误 |
| 上传可见状态 | Passed：真实 Vite 页面挂载生产 FileUploadModal 与 Ant，受控 HTTP 下验证原生 open DOMException 的 error/提示/禁提交、主动删除原生 abort 1 次且 readyState 0、无错误 toast、迟到成功 0、HTTP 409 后删除重传并恢复提交；浅色 1440、深色 1024/768 截图经稳定 DOM 与有限动画检查 | 同步失败曾因列表尚未刷新而缺失 error；修复后读取真实 DOM 和 XHR 原生事件。此证据不是完整 Extensions 真后端 E2E |
| SSR 宿主 | Passed：最终独立 lifecycle 5 项、folder 3 项、PDF 1 项，共 9 项，owned cache leftovers 为 `[]` | 早期配置失败、configureServer/buildStart 后期失败、close 抛错/重复 close；回读 watcher.closed、cacheDir ENOENT 与原错误对象 |

失败负控在独立进程或派生模块中执行，不修改生产源码或运行服务：暂存错误哈希使 4 个固定字节案例失败；并发预算改为 11 和恢复 async 句柄分别破坏预算与真实 Ant 取消断言。上传七项补充负控恢复缺失同步处理、取消错误通知、迟到进度/错误、消费通知前未结束 Promise、未等待列表刷新，均在目标断言失败；真实受控 AUpload 的四种同步准备失败验证刷新边界。

SSR 负控恢复 client discovery 时，实际 optimizer 存在而预期 undefined；省略初始化 catch 的 close 时，configureServer/buildStart 两个案例均因 watcher.closed 为 false 失败。测试子进程退出 1，harness 确认正确原因后退出 0，最后只回收自己拥有的目录。前一负控没有确定性复现历史 close/目录重建交错，事故因果的推断边界仍由复盘说明。

历史验证的可复核入口如下；后端 HTTP/worker 命令在已经配置测试账号与存储的隔离 Compose API 容器内执行，前端命令在 `frontend` 目录执行：

```bash
# 隔离 PG/Redis 已预置，仓库根目录
uv run --project backend --no-sync --group test pytest backend/test/integration/services/test_agent_stop_recovery.py backend/test/integration/services/test_thread_priority_inputs.py -q --tb=short
uv run --project backend --no-sync --group test pytest backend/test/integration/services/test_session_cooperation.py backend/test/integration/services/test_run_lifecycle.py -q --tb=short

# 隔离 API 容器，HTTP fixture 已注入 TEST_USERNAME / TEST_PASSWORD
uv run --no-sync --no-dev pytest test/integration/api/test_knowledge_upload_staging.py -q --tb=short -ra
uv run --no-sync --no-dev pytest test/integration/api/test_graph_build_status.py -q --tb=short -ra
uv run --no-sync --no-dev pytest test/e2e/test_document_parsing_artifacts_e2e.py::test_knowledge_worker_hosts_document_resources_and_file_delete_reclaims_objects -q --tb=short -ra
uv run --no-sync --no-dev pytest test/e2e/test_agent_lifecycle_e2e.py test/e2e/test_agent_lifecycle_extended_e2e.py test/e2e/test_session_cooperation_e2e.py -q --tb=short -ra

# frontend 目录
node --test test/unit/knowledgeUploadQueue.test.js test/unit/file_upload_folder.test.js
node --test --test-concurrency=1 test/unit/testServerLifecycle.test.js test/unit/file_upload_folder.test.js test/unit/pdfPreviewAssets.test.js
```

浏览器探针使用 `playwright-cli run-code --filename=frontend/test/browser/knowledgeUploadQueue.js`。最终完整验证已执行 `pnpm run test:unit`（770 passed，0 failed/skipped/cancelled，62.16 秒）、`pnpm run lint:check`、`pnpm run build`（含 typecheck），host 后端完整 unit 为 3080 passed。结束回读最近 30 分钟创建的测试 cacheDir 残留为 0。工程契约、checker 66 项及 docs build 也已通过；这些均是合并前交付证据。

### 持续执行与验证限制

Inspected：`.github/workflows/system-tests.yml` 选择原件暂存和图谱 HTTP oracle，`scripts/ci_run_service_integration.sh` 选择停止恢复等 PG oracle，既有 frontend unit workflow 自动选择队列、状态与宿主生命周期用例；失败会使对应 gate 非零退出。原组件的调度/XHR/统计实现及对应统计源码正则断言已移除。

Not run：远程 CI、完整 Extensions 页面连接真实后端的浏览器 E2E、非空图谱的外部 LLM/向量 provider 探针、外网 URL 成功抓取与 URL 安全拒绝的真实 HTTP 探针。URL 内容源和认证适配在 ASGI 暂存测试中被替代，fetcher 安全由单测验证；不能把这些边界扩大为外部 provider 成功。默认 Compose api/frontend 未运行导致规定命令在容器内检查开始前失败，host 与隔离拓扑结果单独成立。

旧能力不存在：三个路由各自的暂存序列、路由内图谱提交编排、失败/取消入口重复的暂停派生、接收与查询之间直接耦合恢复 JSON 键，以及弹窗内文件队列/XHR/聚合与对应源码正则测试均已移除。

重新引入条件：出现具有不同存储、去重、生命周期、来源时序或独立客户端转换要求的真实消费者，并有持久事实和边界测试支持时，重新裁决相应边界。

### 本次文档整理的复核

Inspected：逐项核对合并前记录、当前 Owner 和入站引用，仅整理决策与相对链接，保留事故复盘及范围外决定。本次产品回归为 Not run；上文的产品 Passed 均为既有执行记录。本次文档 gate 与历史压缩后的树一致性由交付核验单独记录，不沿用历史构建或测试次数作为新执行结果。
