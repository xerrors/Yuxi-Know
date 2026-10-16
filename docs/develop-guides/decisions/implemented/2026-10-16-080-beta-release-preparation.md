# 0.8.0 Beta 发布准备

状态：implemented
类型：process
Owner：docs/develop-guides/releases/0.8.0.md

## 问题

0.8 的功能决定分散在多个记录中，连续修复和替代设计不能直接作为面向用户的更新项。开发版本引用、依赖锁和 CI 分支需要与 beta 候选一致，同时避免向主仓库写入。

## 决策

### 实现方案

候选分支为 `develop/0-8-0`，版本脚本同步 `0.8.0.beta1`；uv 将 Python 包版本规范化为 `0.8.0b1`。六个质量 workflow 的开发分支匹配替换为当前分支，保留 main、PR、tag、既有 jobs 与路径过滤。发布 workflow 测试分别拒绝恢复旧分支、漏配当前分支及同时残留旧分支，不增加平行 job 或降低门禁。

后端锁定 Docling Slim 2.132.0、LangGraph SDK 0.4.4、MCP 1.30.0 和 multidict 6.9.1，保留当前 MCP 1.x 消费契约。Web 锁定 Vue 3.5.44、DOMPurify 3.4.17、js-yaml 5.4.3，docs 使用 Vue 3.5.42，两者覆盖 source-map-js 1.2.2。修正两处既有单测的外部环境依赖：检索默认值测试隔离模型目录查询，压测探针子进程固定 backend 工作目录；原业务结果断言保持有效。

[独立更新页](../../releases/0.8.0.md)按用户场景合并相对 `v0.7.3` tag 的变化。Decision 负责定位，源码、公开契约和测试确认最终行为；中间 Schema、旧沙盒回收行为和已被取代的 Agent 创建方案不作为最终功能。历史 changelog 只增加入口，导航、README、快速开始、部署参考和 roadmap 同步。Beta 不批量归档 Decision。

候选源码获取指向 `Yuchuan925/Yuxi:develop/0-8-0`。远端写入只面向该 fork 分支；版本材料不表示 tag、GitHub Release 或 npm 包已经发布。原工作区的两处前端修改及两份未跟踪调研保留，不进入发布提交；候选前端和文档在排除这些文件的独立 worktree 中验证。

## 替代方案

- 把 Decision 逐条复制到 changelog：放大实现过程，重复列出已替代行为。
- 只修改版本号或 manifest：不能证明生产锁、依赖和执行环境可用。
- 批量格式化所有文件并同时归档记录：引入无关 diff，提前冻结 beta 仍需维护的决定。
- 为清零告警而强制替换 Markdown 渲染器或跨版本覆盖间接 KaTeX：改变现有渲染消费者，缺少独立兼容性目标；本准备保留当前 high 门禁并明确剩余告警。

## 后果

用户可从同一页了解最终功能、仅全新部署的要求、Cube/KVM 前置、公开 API 与 CLI 不兼容边界，以及尚未验证的范围。候选交付需要对应提交的远端检查，不能用本地通过冒充 GitHub 检查成功。

Web 生产依赖仍有 [markdown-it 中等级性能告警](https://github.com/advisories/GHSA-253c-mchw-3w2r)和[间接 KaTeX 低等级告警](https://github.com/advisories/GHSA-238p-pmpm-9mq7)。后者由 `@vscode/markdown-it-katex` 引入 0.16.47，直接 KaTeX 已为 0.18.4。现有审计按 high 阈值拒绝，达到阈值不表示全部告警清零；剩余风险继续在候选说明公开。

## 验证

以下命令由本地执行。Compose 测试使用独立项目、空 PostgreSQL、Redis、MinIO、Milvus、Neo4j 及私有配置，未操作原开发实例的数据；模型回复来自确定性 HTTP 重放，不产生真实供应商可用性结论。

- `python3 scripts/verify_engineering_contracts.py`：Passed。
- `python3 -m unittest scripts.test_verify_engineering_contracts scripts.test_bump_version scripts.test_release_workflows scripts.test_dependency_update_policy`：Passed，84 项；包含旧分支替换与残留的负向案例。
- `uv lock --project backend --check`、`make audit-dependencies`：Passed；生产后端和 docs 无已知告警，Web 为 1 low、1 moderate，CLI 无告警；现有 Python/Node 审计负控通过。
- `uv run --project backend --no-sync --group test pytest backend/test/unit -m 'not slow' -q`：Passed，2764 项，无跳过；包含真实 Office/PDF 解析夹具与根目录部署配置检查。初跑的 3 项失败分别来自 Redis 名称解析与子进程目录依赖，隔离修正后目标 15 项及完整集合通过。
- `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q`：Passed，2703 项、61 skipped；容器未挂载根目录导致的配置范围由宿主完整集合补齐。
- `docker compose exec -T api uv run --no-sync --group test pytest test/integration/api/test_knowledge_mcp.py test/integration/api/test_mcp_router.py -q`：Passed，23 项，真实 HTTP、权限、PostgreSQL 与 MinIO 回读。
- `docker compose exec -T api uv run --no-sync --group test pytest test/integration/services/test_schema_migration_version.py -q`：Passed，19 项，真实 PostgreSQL 拒绝不兼容版本并保持数据不变。
- `bash backend/test/run_tests.sh e2e`：Passed，39 项、无跳过，624.33 秒；真实 API、worker、SSE、Cube、文件与最终持久结果。首轮因隔离目录不在嵌套节点实际共享的两项根内而失败并中止；修正本地测试挂载后，目标 2 项及完整集合通过，没有改 oracle 或放宽断言。
- `docker compose exec -T api uv run --no-sync --group test pytest test/e2e/test_milvus_text_retrieval_e2e.py test/e2e/test_document_parsing_artifacts_e2e.py -q`：Passed，3 项、150.55 秒；真实 worker 索引、三种检索模式、来源行号、重建与删除，以及附件/知识解析资源的数据库、MinIO 和文件字节回读。
- 独立候选 worktree 执行 `pnpm run lint:check`、`pnpm run test:unit`、`pnpm run build`：Passed，629 项；同时覆盖类型检查。`pnpm --dir docs run build` 通过，构建产物包含新页面、功能与候选状态；源码相对文件链接检查通过。
- `cd packages/yuxi-cli && npm run typecheck && npm test && npm run pack:check`：Passed，15 项；打包检查不上传 npm。
- 锁定 Ruff 0.16.4 的 `ruff check backend/yuxi`、`ruff check --select I backend/yuxi`、`ruff format backend/yuxi --check` 和 `git diff --check`：Passed；只整理本次触及测试的导入，不批量格式化无关源码。
- `docker build --file docker/api.Dockerfile --tag yuxi-beta1-validation-api:0.8.0.beta1 .`：Passed；空库实例 readiness 和包元数据回读为 `0.8.0b1`，Schema 回读为 business 4、knowledge 1。生产 Compose 的必填配置解析通过，未启动完整生产拓扑。

独立 Reviewer 不继承开发上下文，复读完整 diff、需求、源码及证据，指出的首页 Cube 前置和已取代 MCP 创建表述已修正；测试隔离与依赖修复增量复核通过。

远端 CI 的最终结果由 fork Actions 对应 SHA 的检查拥有，本记录只保存本地验收，不能证明远端通过。Not run：自托管 runner 上的系统检查、真实供应商/语料质量、生产成套备份恢复、节点重启恢复及完整产品浏览器验收。fork 的 runner/Actions 策略查询返回 403，不能推断其配置状态；主仓库 runner 查询为空也不作为 fork 结论。候选暂不创建发布 tag、Release 或上传 npm，等待这些发布条件收敛。
