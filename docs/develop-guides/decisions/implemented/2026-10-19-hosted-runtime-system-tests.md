# 完整系统测试迁往 GitHub 托管执行器

状态：implemented
类型：process
Owner：.github/workflows/system-tests.yml

## 问题

完整系统测试需要可用的 Cube、共享目录和业务服务拓扑。托管探针只能证明沙盒执行，完整 API、worker、恢复与存储隔离还需要在相同托管环境中验证，避免依赖用户维护外部服务器。

常规系统 CI 的沙盒选择及 Cube 探针触发策略由[container 运行链路决定](2026-10-23-container-runtime-ci.md)部分取代；本记录的真实 Cube 验证结果仅对应其指定提交与环境。

## 决策

### 实现方案

两个 job 使用 ubuntu-24.04，在各自临时机器上复用 Cube 安装与正式模板准备脚本，再运行原有 Compose 与全部测试步骤。Compose 环境生成脚本从 Docker bridge 获取容器可达的宿主地址，统一使用 /data/shared 下的独立状态目录，并为项目 Redis、MinIO 和 Milvus 健康接口选择不与 Cube 冲突的宿主端口。应用启动与测试成功标准保持在现有 Owner，不增加降级或跳过。

Cube v0.7.3 的[网络端口分区](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.3/docs/architecture/network.md#7-port-mapping)将 10000–19999 分配给宿主临时端口，20000–29999 分配给沙盒映射，30000–65535 分配给 SNAT。CI 的 Redis、MinIO、Milvus 服务与健康接口均映射到 10000 以下，保留容器内部端口；真实 Compose 展开检查及负控拒绝落入 Cube 端口范围的映射。

工作流覆盖被调用的 Cube 准备脚本和模板路径。镜像构建成功后立即保存层缓存，后续业务失败也保留可复用镜像层；失败时保留拓扑与资源诊断，通过真实后台作业恢复和 API/worker/Agent/沙盒 E2E 证明结果。

附件服务用例沿用输入队列 fixture 的 `test_queue` 来源，在真实 PostgreSQL、MinIO 和文件系统上分别验证接收与显式消费。公开用户输入自动恢复暂停队列的行为由现有 HTTP/E2E 用例验证；附件测试保留原有消费前后、回滚和文件字节断言。

HTTP 附件拒绝测试通过独立会话建立真实附件归属，并从 PostgreSQL 回读该前置事实；被拒绝的目标会话保持零 Input、零回执、零 Run 和零消息。准备归属时允许公开输入正常消费，清理通过指定 Turn 的取消与终态回读完成，不再假设公开输入维持暂停状态。

公开附件的待消费快照与取消通过真实 worker 和阻塞重放保持排队，模型开始阻塞后才发送目标 Input；图片产物测试在读取字节后取消并回读消费 Turn 的终态。进程丢失测试从接收服务准备暂停队列，保留独立消费进程的真实退出、PostgreSQL 消费投影、长期 worker 补投或租约恢复，以及 HTTP 终态与产物回读。

普通用户的阻塞 Agent 使用随 Agent 创建的专属 Skill，依照真实 Agent 可见性预加载，重放服务继续检查实际 Skill 内容与工具依赖。公开附件验证紧随运行时基线检查执行，尽早发现输入与文件边界失败；所有业务验证保持无条件阻断步骤，失败继续使 job 失败。

容器内测试入口使用 `uv run --no-sync --no-dev`，直接消费正式 API 镜像构建时安装的测试依赖；测试进程不重装 root 拥有的项目或下载开发工具。shell 回归检查固定此执行契约，并确认恢复测试失败仍解除 shipping worker 的暂停。

跨用户和 Key 终端用户的重放用例复用同一专属 Skill fixture，保留原有管理员共享 Skill 的验证分支。取消和租约失效后的暂停状态以是否仍有 pending Input 为准：空队列保持未暂停，真实 pending 队列的暂停和恢复继续由现有用例证明。

公开输出适配器仅在完成快照提交成功后更新内存 item 的 completed 状态。取消与模型结束竞争导致普通输出写入被拒绝时，已展示正文仍可经受限取消快照落库；真实 lease、当前 Run 和现有公开 item 的校验继续由 repository 执行。

环境模板的空模型和网络搜索配置使用独立注释行，避免 Compose 将空赋值后的说明解析为实际凭据或供应商。真实 Compose 配置展开检查回读 API 与 worker 的搜索配置空值，设置恢复仍通过原有 HTTP 和 worker 用例验证。

沙盒环境变量测试先写临时文件，再以同目录原子重命名发布就绪标记。宿主观察到标记时内容已经写完，避免把 shell 创建空文件与写入正文之间的窗口误判为环境变量丢失；原有进程快照、HTTP 新值、休眠唤醒及不匹配断言保持不变。

公开附件删除测试在阻塞 Turn 完成后，从 PostgreSQL 等待所属 Run 的 `runtime_cleanup_pending` 清除，再执行原有删除与快照断言。业务终态与运行时清理是独立事实，附件服务继续在清理未完成时拒绝删除。

## 替代方案

- 继续注册 self-hosted runner：用户没有可供维护的服务器，托管 Cube 已验证可行。
- 只保留轻量测试与 Cube 探针：不能证明完整系统链路。
- 修改启动依赖或跳过耗时用例：削弱原有业务与隔离验收。

## 后果

两个系统 job 各自持有完整拓扑与 Cube，互不停止对方服务；用户无需提供公网服务器、Cube 地址或密钥。完整拓扑的容量在 ubuntu-24.04 标准托管机器上通过实测，Cube 安装与模板构建仍有网络和磁盘开销。固定版本的成功结果不承诺未来执行器或 Cube 版本始终兼容。

确定性模型与供应商重放覆盖业务和协议边界；带真实凭据的外部供应商可用性仍由独立探针证明。

## 验证

提交 `90c97493` 的 [Runtime System Tests](https://github.com/xerrors/Yuxi/actions/runs/39254561521) 两个 job 均成功。后台任务验证首次 ARQ 发布失败、shipping worker 启动恢复、域失败钩子及真实 HTTP 作业创建；主任务完成全部原有验证，包括 41 项 Agent E2E、并发取消恢复、28 项真实沙盒测试、HTTPS 协议及 Search/Fetch 的 worker 配置切换与恢复，均无 skip。

同一提交的工程契约、Ruff、后端 unit、前端质量、文档构建、依赖审计与独立服务集成均通过。独立服务集成在共享 API 与 Cube 不可达时执行 318 项真实 PostgreSQL/Redis 测试。

`python3 -m unittest scripts.test_ci_resource_boundaries` 使用真实 Compose 展开检查共享路径、端口和配置空值；恢复外部 runner、遗漏 Cube 准备、共享目录不一致、端口占用 Cube 范围或把注释当配置均使断言失败。宿主地址无效或非托管执行环境在副作用前拒绝。

附件服务测试在修复前为 4 failed、9 passed，恢复正确准备边界后 13 passed；完成快照竞争的回归在旧代码上因 completed 状态阻止部分正文保存而失败；原模板在真实 Compose 展开时将说明当作供应商，空值断言失败。修复后的业务结果由上述完整系统运行验证，保留数据库、文件、对象和协议回读。
