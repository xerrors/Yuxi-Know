# WeKnora 内置 MCP 对标研究

本文面向 Yuxi MCP 贡献者，比较只读知识库接入中的模型使用体验与权限边界。当前 Yuxi 契约和验收入口由[知识库 MCP 接入](../advanced/knowledge-mcp.md)拥有；本文是研究参考，不扩展工具或授权范围。

## 证据版本与范围

2026-10-15 通过腾讯官方 GitHub API 解析 WeKnora `main`，固定在 `c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d`，读取该提交原始源码。下文链接固定到此版本。上游独立 Python `mcp-server` 已明确弃用，推荐在「设置 → 发布与集成 → MCP Server」创建内置端点；旧目录中的租户、模型和会话管理工具不计入内置能力。[弃用说明](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/mcp-server/README.md)

Yuxi 对照对象为工作树的 MCP 适配器、共用知识库服务、Schema 和接入文档。只读检索是本研究的目标；写入、Agent 执行、Wiki 和新增凭据模型各有独立业务边界。

## 能力类别与关键差距

| 比较项 | WeKnora 固定版本 | Yuxi 当前实现 |
| --- | --- | --- |
| 部署与协议 | 主 API 进程内置 stateless Streamable HTTP，路径带端点 ID | 主 API 进程内置 stateless Streamable HTTP，固定 `/api/mcp` |
| 检索与阅读 | 语义/关键词搜索、正则候选检索、文档列表与按 chunk 续读 | 内容检索、文件名搜索、文件内关键词/正则定位、按行窗口续读 |
| 模型指导 | 初始化 instructions、详细工具用途与参数说明 | 初始化指引与五个工具说明串联发现、检索、定位、原文核对和分页 |
| 结果格式 | 文本与 structuredContent；搜索结果保留文档/chunk 身份 | 保留 JSON 文本，同时返回 structuredContent；列表结构包装为 knowledge_bases |
| 认证与范围 | 每端点独立 token、KB allowlist、工具 allowlist | 复用用户 API Key，每请求认证，每调用解析用户可见库 |
| 调用预算 | 按端点限流，默认每分钟 60 | MCP 适配器没有独立端点限流 |
| 其他业务 | 综合问答、Wiki 与可选文档写入 | 五个只读知识库工具 |

服务与结果装配见 [server](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/mcpserver/server.go)，检索输入和结果衔接见 [retrieve](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/mcpserver/tools_retrieve.go)。WeKnora 指导先列知识库，再按问题选择检索方式，并用结果中的文档 ID 阅读来源。已检查的内置服务注册没有声明 MCP prompts、resources 或工具 outputSchema；初始化 instructions 不能据此表述成 prompt 模板能力。

WeKnora 的 grep 先从索引召回候选，再验证正则命中，不能推断为穷尽全部分块。文档读取按 chunk 阅读顺序分页；Yuxi 按原文行号定位和读取，参数与返回值应继续服从各自业务语义。[retrieve](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/mcpserver/tools_retrieve.go)、[read](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/agent/tools/read_document.go)

## 三项小范围补齐

Yuxi 当前实现采用以下三项协议层改进，继续复用已有服务与输入 Schema，实际验证结果由接入文档、测试和交付记录承载。

1. **工具选择与串联说明。** instructions 与工具 description 解释 list → query/search_file → find/open；写清 file_id 来源、文件名与正文搜索的区别、行号与偏移的起点、下一窗口及来源引用。收益是模型能使用已有能力完成检索后核对原文。
2. **兼容的结构结果。** 成功结果保留 JSON 文本，并附 structuredContent；list_kbs 的结构结果使用 knowledge_bases 对象包装，文本继续保留原列表。WeKnora 的 jsonResult 与共享 Agent 工具转换也同时支持文本和结构对象。[结果转换](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/mcpserver/server.go)、[JSON 结果](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/mcpserver/tools_retrieve.go)
3. **安全的失败恢复指引。** 400 提示核对参数与能力，404 提示重新发现可见资源，500 提示重试或联系管理员。WeKnora 也在范围或能力失败时提供下一步，但部分路径直接返回 err.Error()；Yuxi 保留固定错误分类和文案，避免底层诊断与资源细节泄露。[范围错误](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/mcpserver/scope.go)、[能力错误](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/mcpserver/tools_wiki.go)

## 暂缓范围与接入体验

WeKnora 的 MCPEndpoint 持久模型拥有独立 mcp_ token、KB 范围和工具集合。token 以 SHA-256 摘要保存，创建或轮换时返回完整值；每次 HTTP 请求运行认证。tools/list 过滤之外，tools/call 再次执行 allowlist guard，知识库与文档仍经过真实访问检查。[模型](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/types/mcp_endpoint.go)、[认证](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/middleware/mcp_endpoint_auth.go)、[scope](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/mcpserver/scope.go)

按 KB 缩小凭据范围有实际价值，但需要持久化、管理接口和授权证据；不能靠 schema 或说明文字实现。端点限流最高每分钟 6000，Redis 滑动窗口不可用时退回进程内计数，不能宣称异常时仍严格跨副本限流。这些能力适合有明确消费者时单独立项。[端点服务](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/application/service/mcp_endpoint.go)、[限流器](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/ratelimit/limiter.go)

WeKnora 集成页提供端点配置、一次性 token、URL 和三种配置片段：原生 HTTP JSON、Claude Code 命令、mcp-remote 的 stdio 桥接。Yuxi 已有 OpenCode 的配置和验收路径，多客户端示例可按真实需求补充，无需先复制端点管理界面。[界面](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/frontend/src/views/integrations/McpServerIntegrationSettings.vue)、[配置生成](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/frontend/src/views/integrations/mcpServerIntegration.ts)

写入、Wiki 和 ask 会扩大业务范围。尤其 ask 虽包含在端点默认工具集合中，其 MCP annotation 明确为 readOnlyHint=false，会创建会话和消息并运行配置的 Agent；它不能进入 Yuxi 当前只读工具集合。[默认集合](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/types/mcp_endpoint_tools.go)、[ask](https://raw.githubusercontent.com/Tencent/WeKnora/c40b33ecc34f5a2c33bc47d33e33c577e2ae1c2d/internal/mcpserver/tools_ask.go)

## 研究验证边界

Inspected：读取固定提交的官方源码和 Yuxi 当前相关实现。Not run：未部署或调用 WeKnora，未验证其索引、数据库、跨空间授权、Redis 降级或外部客户端连接。源码研究不替代 Yuxi 的协议结果回读、真实 HTTP 集成与原文核对，最低证据见[测试规范](./testing-guidelines.md)。
