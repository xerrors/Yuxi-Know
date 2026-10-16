# WeKnora 接入 Yuxi：知识库连接器与 MCP 取舍

本文面向 Yuxi 集成开发者，回答 WeKnora 能否作为知识来源接入、现有 MCP 能否连接，以及哪条路径适合正式集成。前置知识为 Yuxi 的知识库与 Agent 工具边界。完成标准是把可复用入口、权限差异、结果结构和仍需实测的验收项落到源码。本文是选型调研，不代表已接入、部署或通过产品链路验证；不实施存储替换、数据迁移、双写和远端文档管理。

本页的“当前”均指下述调研基线。Yuxi 的后续飞书连接器及权限决定见[飞书只读连接器](../decisions/implemented/2026-10-16-feishu-readonly-connector.md)，运行时能力以源码与用户文档为准。

## 结论与适用假设

可以接入。若目标是“在 Yuxi 知识库列表选择 WeKnora，并让现有 Agent 用同一套知识检索与片段引用能力”，推荐增加调用 WeKnora REST API 的只读知识库连接器。若目标是“先让某个 Agent 使用一组 WeKnora 工具”，现有出站 MCP 可连接其原生 Streamable HTTP 服务，适合先验证效果。两种路径都需要 WeKnora 独立运行。[Yuxi 连接器入口](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/knowledge/factory.py)、[WeKnora API 选择](https://github.com/Tencent/WeKnora/blob/main/website-docs/04-api/01-api-overview.md)、[WeKnora 原生 MCP](https://github.com/Tencent/WeKnora/blob/main/website-docs/03-features/08-mcp.md)分别拥有这些事实。

本建议假设文档上传、解析、索引和数据源同步由 WeKnora 管理，Yuxi 消费检索结果。用 WeKnora 替换 Yuxi 的内置知识引擎、让 Yuxi 上传并管理 WeKnora 文档、或让两边同时维护同一份知识，是不同范围；只读连接器与 MCP 配置均不会自动完成这些目标。这里的推荐是基于当前契约的推断（`Inferred`），需要后文的真实联调才能形成实施决定。

## 证据基线

调研日期为 2026-10-16。Yuxi 本地核对基线为 `30d60bcd2348f5325ee8e3228ae78c6388cd9487`。调研时 WeKnora 最新正式版本为 [v0.8.3](https://github.com/Tencent/WeKnora/releases/tag/v0.8.3)，GitHub 发布时刻为 `2026-10-14T07:53:24Z`，tag 指向 `3e22822c1d2397be730c458c7539d0eb8c113a24`；同时核对 main `2fbfb4471581cd5e7d731bc7a2d443fe7d8e95b5`（提交时刻 `2026-10-15T23:54:14+08:00`）。本文涉及的 MCP 工具目录、认证中间件、MCP server、检索类型以及检索入口在该 tag 与 main 之间无差异；main 的其他新增 API 不作为本次集成前提。

方法为浏览官方仓库与 Release、浅克隆官方源码、按路由到服务和结果序列化核对，状态为 `Inspected`。外部事实只采用 Tencent/WeKnora 一手来源。站内的[广泛能力比较](./weknora-knowledge-base-comparison-research-2026-10-11.md)提供背景，本页聚焦集成；涉及当前实现时以本页固定基线和源码为准。

## WeKnora 对外提供什么

### REST：适合受控的知识检索与文档管理

WeKnora 业务 API 前缀为 `/api/v1`，机器调用使用 `X-API-Key`。空间级 Key 绑定一个空间；受限 Key 按 capability 与知识库白名单授权，路由未声明 Key 策略时默认拒绝。检索需 `retrieve`，内容写入需 `ingest`，知识库生命周期管理需 `manage_kbs`；集成只读查询无需 full-access Key。Key 也支持外部主体 Header，但这需要空间配置与调用者显式传递，不能据此推断两个系统的用户权限已经互通。[认证与权限 Owner](https://github.com/Tencent/WeKnora/blob/main/website-docs/04-api/01-api-overview.md)、[API Key 路由守卫](https://github.com/Tencent/WeKnora/blob/main/internal/middleware/api_key_gate.go)。

| 当前需求 | 最小接口 | 关键语义 |
| --- | --- | --- |
| 选择远端知识库 | `GET /api/v1/knowledge-bases` | 列表受 Key scope 限制；可据此核对配置中的远端 KB ID |
| 为 Yuxi Agent 取检索片段 | `POST /api/v1/knowledge-search` | 无会话；`query`、`knowledge_base_ids`、`match_count`；走召回、rerank、合并、截断 |
| 检查底层召回 | `POST /api/v1/knowledge-bases/:id/hybrid-search` | 默认不 rerank；可传预计算向量；多库要求嵌入模型一致 |
| 远端文档详情与进度 | `GET /api/v1/knowledge/:id` | 回读 Knowledge 与 `parse_status`；批量读取有 `/knowledge/batch` |
| 上传、URL 导入、Markdown 文档 | `POST /api/v1/knowledge-bases/:id/knowledge/file`、`/url`、`/manual` | 文件用 multipart；写入接口与查询是独立能力 |
| 读原文件或预览 | `GET /api/v1/knowledge/:id/download`、`/preview` | 需要单独适配远端文件响应和授权 |

端点与参数以上游[知识库 API](https://github.com/Tencent/WeKnora/blob/main/website-docs/04-api/02-api-knowledge.md)、[知识检索 API](https://github.com/Tencent/WeKnora/blob/main/website-docs/04-api/02-api-chat.md)、[知识路由](https://github.com/Tencent/WeKnora/blob/main/internal/router/routes_knowledge.go)、[聊天与检索路由](https://github.com/Tencent/WeKnora/blob/main/internal/router/routes_chat.go)为准。正式连接器优先用 `knowledge-search`；`hybrid-search` 是需要控制原始召回时的选项，不必同时设计两个后端入口。

`knowledge-search` 返回 `{success,data:[SearchResult],meta:{rerank:...}}`。片段包括 `id`、`content`、`knowledge_id`、`knowledge_title`、`knowledge_base_id`、`chunk_index`、`score`、`match_type`，并可带 `source_locators`、图片信息和原文件信息。`meta.rerank.outcome` 区分正常重排、未配置模型、模型失败降级、阈值过滤等结果；HTTP 200 不能据此归纳为“检索效果通过”。连接器应保留远端标识并显式映射到 Yuxi 的片段结构；远端的 score 不直接等价于本地 Milvus 相似度。[结果 Schema](https://github.com/Tencent/WeKnora/blob/main/internal/types/search.go)、[重排诊断契约](https://github.com/Tencent/WeKnora/blob/main/website-docs/04-api/01-api-overview.md)。

文件和 URL 入库后异步解析及建索引。`parse_status` 包括 `pending`、`processing`、`finalizing`、`completed`、`failed`、`deleting`、`cancelled`；源码说明 `finalizing` 时主解析已完成、向量检索可用，但摘要等增强任务仍在执行。因此“接口返回文档 ID”“已可召回”“所有增强任务结束”是三个观察点。若增加写入，必须由远端 Knowledge 状态拥有处理结果，Yuxi 不能在上传成功时宣称全部入库成功。[状态定义](https://github.com/Tencent/WeKnora/blob/main/internal/types/knowledge.go)、[进度与解析接口](https://github.com/Tencent/WeKnora/blob/main/website-docs/04-api/02-api-knowledge.md)。

图片等资源默认可能返回 `resource://` 句柄，需要另行鉴权读取。`resource_urls=public` 可转换成限时匿名链接，但受知识库白名单限制的 API Key 请求该模式会被拒绝。首期只读集成不能假设图片 URL 可以直接在 Yuxi 渲染，也不应把直链写进长期引用。[资源访问契约](https://github.com/Tencent/WeKnora/blob/main/website-docs/04-api/01-api-overview.md)。

### MCP：原生远程端点与有限工具面

当前推荐方案是 WeKnora 内置 `/mcp/:endpoint_id`，使用 Streamable HTTP 与 `Authorization: Bearer <endpoint_token>`，无需部署 Python 桥接进程。端点管理位于“设置 → 发布集成 → MCP Server”，可指定知识库范围、工具白名单、默认问答 Agent 与限流；每个端点有自己的令牌。服务以无状态模式工作。[MCP 文档](https://github.com/Tencent/WeKnora/blob/main/website-docs/03-features/08-mcp.md)、[服务装配](https://github.com/Tencent/WeKnora/blob/main/internal/mcpserver/server.go)。

| 工具组 | 原生工具 | 对 Yuxi 接入的含义 |
| --- | --- | --- |
| 检索阅读 | `list_knowledge_bases`、`search_knowledge`、`grep_chunks`、`list_documents`、`read_document` | 可直接给 Agent 查询和按 chunk 阅读文档；独立于 Yuxi 知识库目录 |
| 问答 | `ask` | 远端生成完整答案并维护自己的会话；单纯消费检索片段时无需启用 |
| Wiki 阅读 | `wiki_search`、`wiki_read_page`、`wiki_index` | 可消费 WeKnora 的 Wiki 内容 |
| 内容写入 | `add_document`、`update_document`、`delete_document` | 默认不勾选；需要 `ingest` 权限；不等价于 REST 全部文档管理 API |

以上 12 个名称以[工具目录](https://github.com/Tencent/WeKnora/blob/main/internal/types/mcp_endpoint_tools.go)为准，默认开启前 9 个读取/问答工具，写工具默认关闭。`add_document` 只接受 Markdown 内容或 URL，没有 multipart 本地文件上传参数；`update_document` 用于文本创建的 Markdown 文档，重新索引异步执行。需要上传二进制文件或管理解析配置时，应调用 REST。[写工具实现](https://github.com/Tencent/WeKnora/blob/main/internal/mcpserver/tools_ingest.go)。

MCP `search_knowledge` 接受 `query`、`mode=hybrid|semantic|keyword`、`limit`（默认 10、最大 30）和可选 `knowledge_base_ids`。结果同时提供面向模型的文本与 `structuredContent`，结构化数据中有 `results`、`count`、`kb_counts`，片段有 `chunk_id` 或 `faq_id`、`knowledge_id`、`knowledge_base_id`、`content`、`score` 等。这是 Agent 工具结果结构，与 REST `SearchResult` 不同，不能共用未经转换的反序列化假设。[检索工具协议](https://github.com/Tencent/WeKnora/blob/main/internal/mcpserver/tools_retrieve.go)、[Agent 片段序列化](https://github.com/Tencent/WeKnora/blob/main/internal/agent/tools/search_knowledge.go)、[MCP 结果适配](https://github.com/Tencent/WeKnora/blob/main/internal/mcpserver/server.go)。

MCP 认证后合成的是端点机器主体，附带由端点工具与知识库范围换算的 API Key scope。知识库列表为空表示该空间全部，不能把“未选择”理解成“无权限”。客户端无法仅通过这个固定令牌继承 Yuxi 当前用户的个人知识库授权；不同授权域需用独立受限端点，或另行实现身份映射。[MCP 认证](https://github.com/Tencent/WeKnora/blob/main/internal/middleware/mcp_endpoint_auth.go)、[scope 构造](https://github.com/Tencent/WeKnora/blob/main/internal/types/mcp_endpoint_tools.go)。

仓库 `mcp-server/` 下 Python 服务已被标记弃用；它通过 REST API Key 调用上游，支持 stdio、SSE 和 HTTP。仅支持 stdio 的客户端可借助 `mcp-remote` 访问新端点，但 Yuxi 支持远程 HTTP，当前场景无需引入这层桥接。[旧包弃用声明](https://github.com/Tencent/WeKnora/blob/main/mcp-server/README.md)、[原生端点配置](https://github.com/Tencent/WeKnora/blob/main/website-docs/03-features/08-mcp.md)。

## Yuxi 的两个接入边界

### 知识库连接器：复用目录、可见范围与引用

当前知识库 factory 注册 `milvus`、`dify` 和 `notion`。`DifyKB` 是可参考的现有 REST 连接器：提供创建参数 Schema，通过异步 HTTP 获取远端结果，归一正文、分数和文件/分块标识。Manager 的 `retrieve` 调用 executor `aquery` 并构造统一搜索输出。新增 WeKnora 类型可以沿用这一扩展边界；它仍需实现 API 请求和结果映射，配置现有 Dify 类型无法直接调用 WeKnora。[factory](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/knowledge/factory.py)、[Dify 连接器](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/knowledge/implementations/dify.py)、[manager](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/knowledge/manager.py)。

`ReadOnlyConnectors` 的 `supports_documents=False`，不承载上传、解析、索引和原文下载。Manager 的原文阅读/查找入口检查此能力，所以继承它只能获得检索型知识来源；WeKnora 的文档阅读 API、原文件下载、图谱和评估不会自动出现在 Yuxi。前端类型和创建表单消费 factory 的动态 Schema，品牌显示还有 `kb_utils.js` 映射。[只读能力契约](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/knowledge/implementations/read_only_connectors.py)、[前端知识库映射](https://github.com/xerrors/Yuxi/blob/main/frontend/src/modules/knowledge/model/kb_utils.js)。

本地 `visible_knowledge_bases` 用当前用户权限与 Agent 选择的知识库求交集，知识工具在执行时复查。正式连接器应把一个本地 `kb_id` 映射到固定远端 KB ID，并由后端强制把该 ID 写入请求，模型不能随意传入其他远端库。REST Key 仍是机器凭据，本地授权与上游 Key 白名单共同形成范围；REST 协议本身不负责同步权限。[可见性服务](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/knowledge/services/access.py)、[知识工具服务](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/knowledge/services/tools.py)。

Agent 的引用收集只识别 `query_kb`、`open_kb_document`、`find_kb_document`、`web_search`，知识引用还受当前可见 KB 集合限制。因此 REST 连接器经 `query_kb` 输出规范片段，可以复用片段引用校验与撤权过滤；这不等价于完整的原文预览和定位。普通外部 MCP 工具结果没有自动进入这条引用链。[引用 Owner](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/services/references.py)。

### 出站 MCP：现有运行时能连接，知识库契约仍需另接

Yuxi MCP 配置保存 URL、固定 headers、超时、enabled 和禁用工具列表，支持 `sse` 与 `streamable_http`，拒绝 stdio 和进程启动字段。运行时使用 `MultiServerMCPClient.get_tools`，按服务 slug 和配置 hash 缓存工具；Agent 显式选择 MCP 或经已授权 Skill 声明依赖后加载。连接 WeKnora 原生端点在配置与传输层面匹配，实际 SDK 协议协商仍需联调。[配置模型](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/extensions/mcp/models.py)、[管理服务](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/extensions/mcp/service.py)、[运行时](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/extensions/mcp/runtime.py)。

执行授权会重查 Agent、账号、MCP 启用状态、禁用工具与 Skill 授权；当前没有把 Yuxi 用户 ID 动态换成 WeKnora 主体，也没有为 MCP 服务套用知识库 `share_config`。同一服务配置的使用者共享固定远端凭据权限。给部门私有知识配置全空间 MCP 端点会绕开预期的本地知识库隔离模型，应先按授权域限制端点范围与使用者。[执行授权中间件](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/runtime/middlewares/authorization.py)、[MCP 管理服务](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/extensions/mcp/service.py)。

工具元数据会记录 MCP 服务标识，但真实工具名保持上游名称；本地与其他 MCP 工具同名时运行时显式失败。WeKnora 的 `read_document`、`search_knowledge` 等名称需在目标 Agent 的最终工具集合中检查，不能假设服务 slug 自动加前缀。Yuxi 自己的入站 `/api/mcp` 用于给外部客户端读取 Yuxi 知识库，与这里的出站接入属于两个方向。[工具合并 Owner](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/extensions/tools/runtime.py)、[入站知识 MCP](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/api/routers/public_v1/knowledge_mcp.py)。

## 如何选，以及首期做到哪里

| 判断点 | REST 只读知识库连接器 | 原生远程 MCP |
| --- | --- | --- |
| 当前是否只需配置 | 需要增加 WeKnora executor 与注册 | 配置模型已匹配；需验证真实连接 |
| Yuxi 知识库目录与选择 | 可复用本地知识库入口 | 作为 Agent MCP 工具服务存在 |
| 当前用户与部门授权 | 复用本地 KB 可见性，再强制远端固定范围；不自动同步上游权限 | 当前共享固定 headers；没有 KB `share_config` 映射 |
| 片段引用、撤权过滤 | 经 `query_kb` 可复用，需规范映射远端标识 | 当前外部工具名不会自动进入知识引用链 |
| 远端阅读、Wiki、问答 | 逐项适配，首期可只做检索 | 上游已提供相应工具，可按端点白名单启用 |
| 上传与原文件能力 | REST 具备，需另行设计状态和文件边界 | 原生写工具仅文本/URL和Markdown更新；无文件上传工具 |
| 适合的当前目标 | 正式的外部知识来源 | 指定 Agent 的试用、Wiki或远端工具调用 |

这张表是对上述源码事实的选型推断。首期建议在现有知识库体系增加 `weknora` 只读类型，配置服务地址、受限 REST Key 和一个远端知识库 ID；使用 `POST /api/v1/knowledge-search` 获取片段，由 Yuxi Agent 组织最终回答。WeKnora 负责文档管理 UI、摄取与索引，Yuxi 保持自己的 Agent、Turn/Run 和本地授权。首期不复制远端索引、不双写，也不替换 Milvus；这是目前最短且能闭合本地知识库语义的路径。

如果用户只需要先判断“Agent 调 WeKnora 搜索是否有帮助”，可在 WeKnora 创建只暴露指定 KB 的端点，仅勾选检索阅读工具，在 Yuxi 中配置 `streamable_http`、`https://weknora.example.com/mcp/<endpoint_id>` 与 `Authorization: Bearer <endpoint_token>`。随后在目标 Agent 中选择该 MCP 服务。这里的端点令牌不能作为 REST 的 `X-API-Key` 使用；对比效果时保留工具输出与来源，不把可调用工具当成已实现 Yuxi 知识引用。

WeKnora 是独立 Go 服务，标准 Compose 部署拥有 app、frontend、docreader、ParadeDB 与 Redis 等组件，另提供 Lite 形态。接入应通过它的公开 API/MCP，独立保存和运维其数据；把 Go 系统当作 Python 库导入或共用 Yuxi Schema 都超出当前契约。使用反向代理访问 MCP 时还需转发 `/mcp/` 路径、认证与 MCP 协议头，并满足长连接设置。[部署 Owner](https://github.com/Tencent/WeKnora/blob/main/website-docs/01-getting-started/02-installation.md)、[MCP 反代要求](https://github.com/Tencent/WeKnora/blob/main/website-docs/03-features/08-mcp.md)。

## 实施前的验证与未验证范围

当前证据可证明扩展点和协议契约存在，无法证明真实检索质量、SDK 兼容性和跨系统权限已经通过。最小联调应固定一个 WeKnora 版本与受限测试空间，使用有唯一事实和明确预期答案的测试文档，从远端 Knowledge 详情及实际检索结果回读状态。

| 验收问题 | 观察结果与负向案例 |
| --- | --- |
| REST 只读检索是否闭合 | 真实 HTTP 返回指定远端 KB 的片段；本地 `query_kb` 输出规范化 `file_id/chunk_id/source`；错 Key 返回失败，远端不可用不能伪装为空结果 |
| 本地授权是否约束远端范围 | 两个本地用户仅一个可见该 KB；另一用户及撤权后的再次调用被拒绝；修改远端 KB ID、传入额外 `knowledge_ids` 不能扩大后端固定范围 |
| 远端 Key 是否保持最小权限 | `retrieve` Key 能检索目标库，访问另一库与上传请求失败；分别回读结果范围与写入后没有新文档的事实 |
| 引用是否可用且能撤权 | 最终答案片段引文与远端正文逐字匹配；本地撤权后引用不继续展示；只读能力下不展示无法使用的原文按钮 |
| MCP 是否真的兼容 | 完成发现/工具目录/调用并回读目标片段；确认 SDK 对协议版本与结构化返回的处理；错误令牌、禁用端点、非白名单工具、越界 KB 均失败 |
| 工具与身份是否受控 | 核对目标 Agent 最终工具名没有冲突；不同使用者不会因共用端点获得超出产品预期的知识范围；MCP 结果保持外部来源语义 |
| 如后续增加写入 | 上传后轮询真实 `parse_status`，覆盖解析失败、异步取消、重复上传、删除后不可检索；远端文件下载需核验 KB 归属和文件边界 |

`Not run`：没有部署或连接 WeKnora 实例，没有可用实例地址与测试凭据，故未执行上述 REST/MCP/文件/权限联调、检索质量对比和浏览器验证。文档构建与本仓库静态 gate 由本任务交付记录报告；它们验证文档结构和仓库约定，不验证 WeKnora 产品行为。
