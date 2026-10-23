# 0.8.0 Beta 发布准备

状态：implemented
类型：process
Owner：docs/develop-guides/releases/0.8.0.md

## 问题

0.8 的功能决定分散在多个记录中，连续修复和替代设计不能直接作为面向用户的更新项。开发版本引用、依赖锁和 CI 分支需要与 beta 候选一致，同时避免向主仓库写入。

## 决策

### 实现方案

候选分支为 `develop/0-8-0`，版本脚本同步 `0.8.0.beta1`；uv 将 Python 包版本规范化为 `0.8.0b1`。六个质量 workflow 的开发分支匹配替换为当前分支，保留 main、PR、tag、既有 jobs 与路径过滤。发布 workflow 测试分别拒绝恢复旧分支、漏配当前分支及同时残留旧分支，不增加平行 job 或降低门禁。

后续候选的开发分支通配规则与版本同步由[开发分支 CI 与 beta2](2026-10-19-development-ci-beta2.md)拥有；本记录保留 beta1 的准备与验收范围。

后端锁定 Docling Slim 2.132.0、LangGraph SDK 0.4.4、MCP 1.30.0 和 multidict 6.9.1，保留当前 MCP 1.x 消费契约。Web 锁定 Vue 3.5.44、DOMPurify 3.4.17、js-yaml 5.4.3，docs 使用 Vue 3.5.42，两者覆盖 source-map-js 1.2.2。修正两处既有单测的外部环境依赖：检索默认值测试隔离模型目录查询，压测探针子进程固定 backend 工作目录；原业务结果断言保持有效。

[独立更新页](../../releases/0.8.0.md)按用户场景合并相对 `v0.7.3` tag 的变化。Decision 负责定位，源码、公开契约和测试确认最终行为；中间 Schema、旧沙盒回收行为和已被取代的 Agent 创建方案不作为最终功能。历史 changelog 只增加入口，导航、README、快速开始、部署参考和 roadmap 同步。Beta 不批量归档 Decision。

更新页标明已核对的提交与日期，只收录该提交可追溯的实现，未提交工作区内容不计入发布范围。部署与执行说明区分默认 Cube 用户 VM 和可选 Run 级容器；来源标注、MCP 故障隔离及 CI 按后续已生效决定更新。历史测试结果链接到所属记录并保留拓扑、时点和未运行范围，不把文档核对或旧探针扩写为当前版本完整验收。

候选源码获取指向 `Yuchuan925/Yuxi:develop/0-8-0`。远端写入只面向该 fork 分支；版本材料不表示 tag、GitHub Release 或 npm 包已经发布。原工作区的两处前端修改及两份未跟踪调研保留，不进入发布提交；候选前端和文档在排除这些文件的独立 worktree 中验证。

## 替代方案

- 把 Decision 逐条复制到 changelog：放大实现过程，重复列出已替代行为。
- 只修改版本号或 manifest：不能证明生产锁、依赖和执行环境可用。
- 批量格式化所有文件并同时归档记录：引入无关 diff，提前冻结 beta 仍需维护的决定。
- 替换 Markdown 公式插件或编写自有插件：扩大渲染语义改动。现有插件只消费 KaTeX 的 `renderToString`，限定依赖边的覆盖可保留解析和渲染入口，并通过兼容性及负向案例验证。

## 后果

用户可从同一页了解最终功能、仅全新部署的要求、两种执行后端的前置与持久化差异、公开 API 与 CLI 不兼容边界，以及尚未验证的范围。候选交付需要对应提交的远端检查，不能用本地通过冒充 GitHub 检查成功。

Web 使用 markdown-it 15.0.2 修复[自动链接的二次复杂度问题](https://github.com/advisories/GHSA-253c-mchw-3w2r)，锁定已发布的补丁版本以避免引入当天新版本及无关传递依赖。`@vscode/markdown-it-katex>katex` 定向覆盖到 0.18.4，修复[原型污染后的继承属性读取](https://github.com/advisories/GHSA-238p-pmpm-9mq7)，并与页面直接导入的 KaTeX CSS 保持同版。插件仍使用原有 `renderToString`、`trust: false` 和后续 DOMPurify 清理；覆盖需要在插件升级时重新评估，不构成对全部 0.16 消费者的兼容承诺。

## 验证

更新页内容核对以 `v0.7.3..97e04174` 的提交历史、页面修订和对应提交的源码为范围（`Inspected`），不读取未提交功能作为发布事实。工程契约检查、检查器 66 项 unittest、两份变更文档的相对链接及构建后锚点检查、`cd docs && pnpm run build` 与 `git diff --check` 通过；文档构建存在非阻断的大 chunk 提示。此次文档更新未重跑产品 HTTP、worker、浏览器或外部供应商链路（`Not run`），下述 beta1 测试及更新页引用的后续记录均保留各自的验证时点与范围。

以下命令由本地执行。Compose 测试使用独立项目、空 PostgreSQL、Redis、MinIO、Milvus、Neo4j 及私有配置，未操作原开发实例的数据；模型回复来自确定性 HTTP 重放，不产生真实供应商可用性结论。

- `python3 scripts/verify_engineering_contracts.py`：Passed。
- `python3 -m unittest scripts.test_verify_engineering_contracts scripts.test_bump_version scripts.test_release_workflows scripts.test_dependency_update_policy`：Passed，84 项；包含旧分支替换与残留的负向案例。
- `uv lock --project backend --check`、`make audit-dependencies`：Passed；生产后端、Web、docs 和 CLI 均无已知告警；现有 Python/Node 审计负控通过。
- `uv run --project backend --no-sync --group test pytest backend/test/unit -m 'not slow' -q`：Passed，2764 项，无跳过；包含真实 Office/PDF 解析夹具与根目录部署配置检查。初跑的 3 项失败分别来自 Redis 名称解析与子进程目录依赖，隔离修正后目标 15 项及完整集合通过。
- `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q`：Passed，2703 项、61 skipped；容器未挂载根目录导致的配置范围由宿主完整集合补齐。
- `docker compose exec -T api uv run --no-sync --group test pytest test/integration/api/test_knowledge_mcp.py test/integration/api/test_mcp_router.py -q`：Passed，23 项，真实 HTTP、权限、PostgreSQL 与 MinIO 回读。
- `docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_schema_migration_version.py -q`：Passed，19 项，真实 PostgreSQL 拒绝不兼容版本并保持数据不变。
- `bash backend/test/run_tests.sh e2e`：Passed，39 项、无跳过，624.33 秒；真实 API、worker、SSE、Cube、文件与最终持久结果。首轮因隔离目录不在嵌套节点实际共享的两项根内而失败并中止；修正本地测试挂载后，目标 2 项及完整集合通过，没有改 oracle 或放宽断言。
- `docker compose exec -T api uv run --no-sync --group test pytest test/e2e/test_milvus_text_retrieval_e2e.py test/e2e/test_document_parsing_artifacts_e2e.py -q`：Passed，3 项、150.55 秒；真实 worker 索引、三种检索模式、来源行号、重建与删除，以及附件/知识解析资源的数据库、MinIO 和文件字节回读。
- 独立候选 worktree 执行 `pnpm run lint:check`、`pnpm run test:unit`、`pnpm run build`：Passed，631 项；同时覆盖类型检查。`pnpm --dir docs run build` 通过，构建产物包含新页面、功能与候选状态；源码相对文件链接检查通过。
- `cd packages/yuxi-cli && npm run typecheck && npm test && npm run pack:check`：Passed，15 项；打包检查不上传 npm。
- 锁定 Ruff 0.16.4 的 `ruff check backend/yuxi`、`ruff check --select I backend/yuxi`、`ruff format backend/yuxi --check` 和 `git diff --check`：Passed；只整理本次触及测试的导入，不批量格式化无关源码。
- `docker build --file docker/api.Dockerfile --tag yuxi-beta1-validation-api:0.8.0.beta1 .`：Passed；空库实例 readiness 和包元数据回读为 `0.8.0b1`，Schema 回读为 business 4、knowledge 1。生产 Compose 的必填配置解析通过，未启动完整生产拓扑。

依赖告警补充验证：`node --test test/unit/markdown_preview_fallback.test.js` 通过 7 项，覆盖行内和块级公式、源行定位、非法命令、禁用可信链接/图片及原型注入宏；相同测试在独立旧锁 worktree 的 KaTeX 0.16.47 上为 6 passed / 1 failed，注入宏被展开为 `POLLUTED`，在 0.18.4 上被拒绝。两组官方自动链接输入（邮件软换行、未知 scheme，各重复 20000）由独立 Node 子进程执行，旧 markdown-it 15.0.0 合计 7827ms，新 15.0.2 为 228ms，均核对邮件链接数 20000；该计时是本机复现结果，不是跨机器性能保证。补丁增量重新执行 `make audit-dependencies`（含负控）、上述 84 项脚本测试、后端 2764 项 unit、前端 lint / 631 项 unit / typecheck / build、docs build 与 `git diff --check`，均通过。候选前端仍在排除用户未提交修改的独立 worktree 中验证。

独立 Reviewer 不继承开发上下文，复读完整 diff、需求、源码及证据，指出的首页 Cube 前置和已取代 MCP 创建表述已修正；测试隔离与依赖修复增量复核通过。

远端 CI 的最终结果由 fork Actions 对应 SHA 的检查拥有，本记录只保存本地验收，不能证明远端通过。推送 fork 分支后没有产生检查；手动触发同一提交的 `trust.yml` 返回 `422: Actions has been disabled for this repository`，确认当前 fork 禁用 Actions。读取 runner/Actions 策略返回 403，runner 配置状态仍不可判定。需要 fork 管理者启用 Actions 并确认 Cube runner 后运行对应提交的完整检查；主仓库 runner 状态不作为 fork 结论。

生产镜像、浏览器主流程、应用成套冷备恢复、worker 崩溃恢复和一次真实 SiliconFlow 探针的补充证据由[本地生产验收](2026-10-16-production-release-acceptance.md)维护。Not run：远端 CI、自托管 runner 上的系统检查、真实语料质量、公网 TLS、真实数据规模灾备、Cube 节点重启及 VM 磁盘恢复和未覆盖的产品页面。候选暂不创建发布 tag、Release 或上传 npm，等待发布条件收敛。

发布复查：fork 的 `trust.yml` 手动触发仍返回 Actions 禁用的 HTTP 422，runner API 返回 403，远端完整门禁未完成。`v0.8*` 远端 tag 查询为空。生产 Compose 从源码本地构建，无自动镜像上传步骤；文档构建可在分支/tag 触发，站点部署只匹配 main。公共 npm registry 查询 `@xerrors/yuxi` 返回 404，CLI 文档已提供源码打包安装；npm 上传属于单独交付，需发布身份与环境配置，不阻塞源码候选获取。
