# 0.8 Beta 本地生产发布验收

状态：implemented
类型：testing
Owner：docker-compose.prod.yml

## 问题

候选已有单测和开发拓扑 E2E，但生产镜像、浏览器及成套恢复缺少直接证据。生产文档承诺 API 只绑定回环地址，Compose 原端口声明实际绑定所有接口；首次创建的 bind mount 目录也不能保证生产 UID 可写。

## 决策

### 实现方案

生产 API 的宿主端口固定绑定 `127.0.0.1`，由 Nginx Web 代理接收浏览器请求。首次部署按[生产部署](../../../advanced/deployment.md)先构建镜像，再用一次性 root 进程只准备三个应用挂载根的数字属主和权限，长驻 API/worker 保持 `1000:1000`。文档同时纠正 worker 健康模块路径，并维护同版本整套状态冷备与恢复规程。

验收从已提交 `8e165238` 加生产端口修正构建独立生产 API、Nginx 前端和 MinIO；没有未提交的用户前端修改或应用源码挂载。Compose project、端口、空状态目录和 Cube 用户文件/Skills 子目录独立，只对 Docker 地址池耗尽使用本地网络子网配置。模型重放是独立 HTTP fixture，不替换应用 API、worker 或存储。

浏览器操作真实产品入口，持久化结果由 SQL、对象、Milvus 查询、文件字节和 DOM 交叉回读。停写并停止本次全部服务后，把应用状态根和两项外置共享目录分别冷备到三个 tar；恢复到不同空目录，保留原状态、数字属主、模式、符号链接、ACL/xattrs 与环境安全密钥。恢复实例复用相同版本镜像，启动前比对冷备 manifest，启动后核对业务结果并提交新对话。测试输出与凭据保存在本地忽略目录，不提交。

## 替代方案

- 继续用开发实例冒充生产：不能证明镜像文件、Nginx 和生产挂载。
- 只导出 PostgreSQL 或只检查 readiness：不能证明对象、索引、反馈和用户文件的一致性。
- 改文档允许 API 公网直连：与通过 Web/TLS 入口接入的部署承诺不符。
- 新建通用备份平台或自动递归修正文件权限：扩大维护面或改变已有数据属主；部署规程和独立恢复证据即可覆盖当前候选要求。

## 后果

候选具备本地全新生产核心拓扑、浏览器主流程和应用数据恢复的直接证据。它不证明公网 TLS、真实数据规模下的恢复时间、所有供应商/语料质量或外部集成权限。

Cube 节点与原开发环境共享，本轮不重启整个节点、不备份其他用户 VM 磁盘。应用冷备不包含 Cube VM Home 和安装的软件；独立节点的磁盘备份、实例身份及重启后原环境恢复需要维护窗口，不能由 worker 崩溃恢复或创建空 VM 代替。

浏览器复现一项非阻塞限制：自动入库已经在后台完成，列表仍可能停留“待入库”；点击刷新后显示已入库和正确 Tokens。文档预览、检索及持久索引结果正确，该验收基线没有修改前端轮询行为；此问题已由[列表终态刷新决定](2026-10-16-knowledge-job-list-refresh.md)修复并补充生产浏览器验证。

## 验证

本轮使用本机 HTTP、合成账号和合成文档；原开发 Compose 与用户未提交修改保持不变。以下是实际命令入口和结果，不代表远端 CI 已通过。

- 独立 worktree 执行生产 Compose `build api frontend minio`、`up -d`：Passed。API/worker 首次因应用目录不可写失败；按首次部署命令准备目录后重新启动，全套核心服务 healthy，`schema-init` 正常结束。API readiness 为 `ready`、`degraded=false`，版本 `0.8.0b1`；SQL Schema 为 business 4 / knowledge 1。
- `docker inspect` 回读 API 的 `HostIp=127.0.0.1`、`Config.User=1000:1000`，应用容器只有三项数据挂载，无源码挂载。API 镜像为 `sha256:ba613d08f66546ec65fd86f1ef955d2b71cdfaa273e83974b3a0eb99799fe95a`，Web 为 `sha256:5b61e5a8c8523dffb3efd0f3821c74c0de964eda10c9ad55b062a64cd5a28404`。
- Playwright Chromium 真实 UI：Passed，管理员首次创建、退出/重登、选择 Agent、发送与点赞、刷新恢复；创建知识库、上传 Markdown 自动入库、手动刷新、检索命中与来源行 1–13、公式预览；个人空间上传、预览；1440×1000 和 390×844、浅/深色截图回读。行内/块公式共 2 个 KaTeX 节点，无 KaTeX error。正常浏览器阶段控制台无 error/warning，停机期间原连接的预期网络错误单独保留，恢复后新浏览器上下文无 error。
- `CUBE_TEST_ISOLATED_TOPOLOGY=1 bash scripts/test_cube_worker_recovery.sh`：Passed，1 项，46.61 秒，覆盖真实双 worker、按 Turn 取消、杀 worker、孤儿命令收尾及新任务文件/Artifact 字节。脚本只接入本轮隔离 Compose。生产镜像补入测试 fixture 后执行；首轮因 `uv run` 尝试在 UID 1000 下重建 root-owned 包元数据而失败，测试环境显式 `UV_NO_SYNC=1`，与 shipping 启动一致；pytest 缓存权限产生 1 warning，无 skip。
- 停机前 SQL 回读 pending/running/cancel_requested Run、pending Input、活跃作业和沙盒命令合计 0，全部 11 项服务停止。三份冷备约 666 MiB，备份前后 manifest 稳定；恢复到不同空状态目录与共享路径，启动前 2261 个文件/目录记录的 SHA256、UID/GID、模式和链接逐项一致。
- 恢复后真实 HTTP、SQL、MinIO、Milvus、Neo4j 与文件回读：Passed。7 个 Turn 的状态/结果归属、Run、Message、2 条反馈、知识文件索引事实、Milvus 文本记录、2 个知识业务对象 SHA256、Neo4j 合成节点标记与 Workspace 文档摘要均与备份前一致。Neo4j 此项只证明存储恢复，非完整图谱提取质量验收。Milvus/Woodpecker 的 `a-bucket` 内部日志对象在启动后维护变化；不把启动后的全部内部对象列表宣称为逐字节相等。
- 恢复后浏览器继续发送新消息并重新加载：Passed，原会话 2 个 completed Turn、2 次完整输出；新浏览器上下文保留原登录状态并重新打开个人文档与公式。此项与恢复前快照比较分开执行，确认恢复实例仍可写。
- `uv run --no-sync --no-dev pytest test/e2e/test_real_provider_e2e.py -q`：Passed，1 项，2.27 秒。临时为隔离实例配置现有 SiliconFlow 凭据，走真实供应商、API、worker、SSE，并核对输出、Turn 和 result Run；结束后清除临时凭据。此项不等于嵌入/重排质量和所有模型验收。
- `uv run --project backend --no-sync --group test pytest backend/test/unit -m 'not slow' -q`：Passed，2765 项，58.27 秒。生产端口回归测试先在旧配置上失败，当前配置子集 7 项通过。
- 生产容器 `uv run --no-sync --group test pytest test/unit -m 'not slow' -q`：Passed，2703 项、62 skipped，64.65 秒；缺仓库根文件的配置检查由宿主 2765 项完整集合补齐。初跑因测试 fixture 未包含 `scripts/seed_initial_users.py` 有 1 项失败，补入该脚本后目标 1 项和完整集合通过；只补测试输入，没有改变 shipping 源码或放宽断言。
- `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts scripts.test_bump_version scripts.test_release_workflows scripts.test_dependency_update_policy`、docs build、`git diff --check`：Passed，脚本测试 84 项。

远端 `trust.yml` 手动触发仍返回 HTTP 422 `Actions has been disabled for this repository`。需要 fork 管理者启用 Actions 并配置专属 Cube runner 后运行最终提交检查。公网域名/TLS、真实部署数据规模灾备和 Cube 节点完整重启/VM 磁盘恢复仍未执行。没有创建 tag、Release 或上传 npm。
