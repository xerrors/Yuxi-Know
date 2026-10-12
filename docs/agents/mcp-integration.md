# 集成 MCP

MCP（Model Context Protocol）让智能体调用外部服务提供的工具。超级管理员在“扩展 → MCP”中添加远程服务器；Agent 可直接选择服务器，Skill 也可声明激活后加载的依赖。

## 支持的传输方式

| 传输方式 | 适用场景 |
| --- | --- |
| `streamable_http` | 新的远程 MCP 服务 |
| `sse` | 仍提供 SSE 接口的远程服务 |

管理接口只接受 `streamable_http` 和 `sse`。Yuxi 不支持 `stdio`，包括内置 MCP 和直接传入的运行时配置，也不接受 `command`、`args`、`env` 进程字段。

## 添加远程 MCP

在“扩展 → MCP”点击“添加 MCP”，填写稳定标识、名称、传输方式和 URL。例如：

```json
{
  "slug": "custom-remote-mcp",
  "name": "Example MCP",
  "transport": "streamable_http",
  "url": "https://example.com/mcp"
}
```

管理接口对应：

```http
POST /api/system/mcp-servers
Authorization: Bearer <superadmin-token>
Content-Type: application/json

{
  "slug": "custom-remote-mcp",
  "name": "Example MCP",
  "transport": "streamable_http",
  "url": "https://example.com/mcp",
  "description": "提供示例查询工具"
}
```

需要认证的远程服务可以配置 HTTP headers、连接超时和 SSE 读取超时。凭证会随着连接请求发送，请只配置必要的 header，并把管理接口限制在可信的管理员范围。

新增服务器立即启用。[创建智能体](./agents-config.md#创建智能体)的高级配置提供相同的独立创建入口，成功后选入 Context；取消或创建 Agent 失败时服务器仍保留。可以在 MCP 管理页点击“测试连接”确认工具发现结果，也可关闭服务器状态；状态关闭时记录仍保留，但不会进入运行时。

## 让智能体使用 MCP

在智能体配置的 MCP 字段中显式选择要直接添加的服务器。该字段默认不添加服务器：

- 未显式配置或显式清空时，不直接加载 MCP 服务器；
- 显式选择后，只使用所选且当前可用的服务器；
- MCP 工具仍会在执行处使用当前用户身份和服务器配置；
- 管理员可以在 MCP 详情页单独禁用某个工具。

共享 Skill 的 `mcp_dependencies` 声明所需服务器。Skill 激活后按需加载这些服务器的工具；预加载 Skill 从首轮加载，均无需在 Agent 的 MCP 字段重复选择。服务器必须由管理员启用，禁用的服务器不会提供工具。

MCP 配置从 PostgreSQL 读取，工具对象按配置哈希缓存。修改连接配置或工具禁用列表后，下一次运行会使用新的配置键。

## 内置远程 MCP

内置 DeepWiki 使用 `deepwiki-official` 标识，通过 `https://mcp.deepwiki.com/mcp` 提供 Streamable HTTP 服务，无需认证即可查询公开 GitHub 仓库。详见 [DeepWiki 官方文档](https://docs.devin.ai/work-with-devin/deepwiki-mcp)。

开发者在 [`builtin.py`](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/extensions/mcp/builtin.py) 的 `BUILTIN_MCP_MANIFEST` 中维护清单：

```python
BUILTIN_MCP_MANIFEST = {
    "mcpServers": {
        "deepwiki-official": {
            "type": "http",
            "url": "https://mcp.deepwiki.com/mcp",
            "extra_data": {
                "name": "DeepWiki",
                "description": "查询公开 GitHub 仓库的文档、架构与代码",
                "icon": "📚",
                "tags": ["内置", "代码", "文档"],
            },
        },
    },
}
```

清单连接字段支持 `type`（`http`、`sse`）或 `transport`（`streamable_http`、`sse`）、HTTP URL、headers、timeout 和 sse_read_timeout。同时声明 type 与 transport 时必须一致。展示字段 name、description、icon 和 tags 放在 `extra_data`，名称缺省时使用清单键。管理表单使用相同清单结构解析，再转换为上面的平铺管理接口字段；`extra_data` 不发送给远端 MCP 客户端。

API/worker 启动时只同步当前内置定义到数据库；运行时直接读取代码中的连接字段。新内置 MCP 默认未添加，管理员需要启用；连接配置不可通过页面修改。管理员的启停与禁用工具列表在同步后保留。全新部署不提供 stdio 数据迁移或退役配置清理。

## 常用管理接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/system/mcp-servers` | 查看服务器；普通用户只得到脱敏基础信息 |
| `POST` / `PUT` | `/api/system/mcp-servers`、`/{slug}` | 添加或修改远程 MCP |
| `PUT` | `/api/system/mcp-servers/{slug}/status` | 启用或停用服务器（对应页面上的添加/移除状态） |
| `POST` | `/api/system/mcp-servers/{slug}/test` | 测试连接并发现工具 |
| `GET` | `/api/system/mcp-servers/{slug}/tools` | 查看工具 |
| `PUT` | `/api/system/mcp-servers/{slug}/tools/{tool_name}/toggle` | 启用或禁用单个工具 |

接口字段和错误响应以实例 Swagger 为准。

已启用 MCP 的建连或工具发现失败时，管理检查、Agent 配置工具装配与 Skill 依赖加载均明确失败，运行不会把故障当作成功的空工具列表继续执行。服务器正常返回零个工具仍是合法结果；未启用服务器不参与运行加载。运行日志包含组件、服务器标识、错误类型与不可用状态。
