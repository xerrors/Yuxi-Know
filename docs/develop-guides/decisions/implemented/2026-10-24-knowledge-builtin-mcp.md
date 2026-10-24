# 知识库工具收敛为内置 MCP 装配

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/knowledge/mcp/client.py

## 问题

知识库查询经 HTTP MCP 后，本地五个工具包装仍复制工具目录、参数 Schema 和结果契约。知识能力需要使用与其他 MCP 相同的 server 粒度装配及 Skill 依赖。

## 决策

### 实现方案

Knowledge MCP 服务端拥有五个只读工具的名称、Schema 与结果。内置 `knowledge` 连接使用平台委托鉴权，`knowledge-base` Skill 以 `mcp_dependencies: ["knowledge"]` 加载服务。删除五个本地 `@tool` 包装、knowledge 本地分类和再导出。

Knowledge 自己拥有 SDK Auth、会话选择、产品读取和引用转换；通用 MCP 层复用现有工具发现与执行。职责与删减范围由[Knowledge 自有 MCP 决定](./2026-10-24-knowledge-domain-mcp-ownership.md)进一步限定。

## 替代方案

- 保留本地包装并校验 MCP 目录：仍有两处参数与说明的事实来源。
- 使用业务专属认证模式：通用装配和管理入口需要识别业务名。
- 把知识选择改为 MCP server 选择：两者分别表达资源范围与服务能力，不是同一语义。

## 后果

知识工具契约只有服务端目录一个来源。会话知识选择独立保留，服务端按当前用户权限与选择求交集；Skill 的知识能力声明使用 MCP 依赖，本地工具依赖不能指向五个知识工具。没有本地检索 fallback，也不提供 Agent 原件下载工具。

## 验证

注册表负向测试检查五个工具名及 knowledge 分类不再本地注册，Skill 测试检查 MCP 依赖。当前传输、执行策略、HTTP 与 worker 的直接证据和未验证范围由[Knowledge 自有 MCP 决定](./2026-10-24-knowledge-domain-mcp-ownership.md)维护，历史单测结果不作为新执行边界的通过证据。
