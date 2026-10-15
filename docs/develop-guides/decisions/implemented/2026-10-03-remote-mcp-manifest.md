# 远程 MCP 清单与内置定义

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/extensions/mcp/service.py

## 问题

MCP 管理表单和内置连接采用不同配置格式，连接与展示字段混合；启动承担已退役配置的兼容处理。v1 只交付远程 MCP，全新部署不需要历史 stdio 迁移。

## 决策

内置定义沿用 PR #1064 的 DeepWiki 远程 MCP 基线，使用 `mcpServers` 清单；`type: http` 归一为 `streamable_http`，展示字段放入 `extra_data`。管理表单使用同一清单解析规则，再提交既有 CRUD 接口。清单解析入口留在前端 extensions 模块，后续创建 Agent 流程可复用。`extra_data` 映射展示列，不进入客户端连接配置。

### 实现方案

`mcp/config.py` 拥有后端清单归一与持久化输入契约，`runtime.py` 在客户端和工具缓存前拒绝非远程传输及进程字段；内置连接仍以代码定义为准。启动只同步当前内置定义，保留管理员启停与工具禁用列表。删除退役配置清理、历史传输禁用及残余进程字段。新库初始化不创建 MCP `env` 列，数据库版本由[首个 Schema 基线决策](2026-10-15-initial-schema-baseline.md)拥有，不提供旧数据库升级路径。

## 替代方案

- keep：保留混合字段和历史兼容，增加全新部署无须承担的维护面。
- narrow：仅切换内置格式，表单与后端仍有不同规则。
- replace：清单统一连接与展示结构，管理 HTTP API 保留平铺字段契约。
- remove：删除全部 MCP 会丢失 Agent 的远程工具能力。

## 后果

MCP 只支持 Streamable HTTP 和 SSE，包括内置、管理接口和直接运行时调用。非当前基线的数据库按 Schema 校验拒绝启动，应使用全新部署环境。DeepWiki 是可选外部服务，新增内置项默认停用，工具发现和调用受网络及提供方可用性影响。

Agent 专属 Skill 由[绑定决策](2026-10-03-agent-bound-skill.md)接续；创建时的 Context 和独立资源入口由[创建流程决策](2026-10-05-agent-create-context.md)接续。

## 验证

- 后端相关 unit：48 passed；全量 `uv run --group test pytest test/unit -m "not slow"`：2442 passed、55 skipped、7 subtests passed。全量后局部简化由相关 unit 48 项和 MCP HTTP integration 14 项重跑覆盖。
- 隔离 Docker API、新建 PostgreSQL v13 数据库：`uv run --no-sync --group test pytest test/integration/api/test_mcp_router.py test/integration/services/test_schema_migration_version.py test/e2e/test_mcp_stdio_security.py -q --tb=short`，24 passed。回读非法创建无记录、非法更新保持原行、展示字段持久化、重复初始化无进程列；实际 MCP 协议对端覆盖成功、空工具与连接失败。Schema 锁测试调用实际迁移模块 Owner。
- 前端 `pnpm run test:unit`：424 passed，包括清单解析、stdio、进程字段、冲突传输、非法 URL、展示数据类型的负向案例；lint、typecheck 和 build 通过。
- 浏览器真实管理页拒绝 file URL；纠正为 HTTP URL 后提交成功，DOM 卡片与独立 PostgreSQL 查询核对创建字段。浅色、暗色和 390px 弹窗已检查并截图；窄屏弹窗宽 358px，左右留 16px，内容可滚动且确认按钮可见。
- 工程契约检查、64 项契约单测与 VitePress build 通过。最终执行命令由 PR 记录。
- 真实 DeepWiki 发现 `ask_wiki_question`、`read_wiki_contents`、`read_wiki_structure`；只读调用 `read_wiki_structure(repoName="xerrors/Yuxi")` 返回实际仓库文档目录。未验证通过模型自动选择 MCP 或跨 worker 调用，本变更不改变该装配链路。

旧能力不存在：源码负向搜索确认没有 stdio 执行分支、command/args/env 配置列、退役 slug 注册、历史传输禁用或迁移 UI。拒绝消息、负向输入和历史决策中的 stdio 文本保留；新库列集合由独立 PostgreSQL 查询反证。

重新引入条件：新的远程 MCP 通过当前清单声明；stdio 只有在产品范围与隔离执行边界重新裁决后才能进入独立提案。
