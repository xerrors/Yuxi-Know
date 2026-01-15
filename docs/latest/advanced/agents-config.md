# 智能体

## 智能体开发

系统基于 [LangGraph](https://github.com/langchain-ai/langgraph) 并通过统一的 `AgentManager` 管理所有智能体。`src/agents/__init__.py` 会在启动时遍历 `src/agents` 目录，对每个包含 `__init__.py` 的子包执行自动发现：所有继承 `BaseAgent` 的类都会被注册并立即初始化，因此只要代码落位正确，就不需要再手动登记或修改管理器。

仓库预置了若干可直接运行的智能体：`chatbot` 聚焦对话与动态工具调度，`mini_agent` 提供精简模板，`reporter` 演示报告类链路。这些目录展示了上下文类、Graph 构造方式、子智能体引用以及中间件组合的范例，新增功能时可以直接复用。

### 智能体元数据配置

每个智能体可以通过在智能体目录下创建 `metadata.toml` 文件来配置元数据信息。这个文件使用 TOML 格式，包含以下字段：

- `name`: 智能体显示名称
- `description`: 智能体功能描述
- `examples`: 示例问题列表（数组格式）

例如，`src/agents/chatbot/metadata.toml`：

<<< @/../src/agents/chatbot/metadata.toml

**注意**：`metadata.toml` 文件是可选的，如果没有提供，系统将使用智能体类的基本属性。

### 创建新的智能体

在 `src/agents` 下新建一个包，保持与现有目录一致的结构：放置 Graph 构造逻辑（通常命名为 `graph.py`），并在包内的 `__init__.py` 中暴露主类。

智能体类必须继承 `src.agents.common.BaseAgent`，同时实现异步的 `get_graph` 方法来返回编译后的 LangGraph 实例，并配置好 `checkpointer`，否则无法从历史对话中恢复。

需要额外上下文字段时，可继承 `BaseContext` 构建自己的配置表单，再把类绑定到 `context_schema`，平台会在 `saves/agents/<module>` 下生成默认配置。

案例1 使用内置工具构建一个极简的智能体，可以动态选择 Prompt 和 LLM：

<<< @/../src/agents/mini_agent/graph.py

案例2 基于MySQL工具，以及自定义 MCP Server 的数据库报表助手。

<<< @/../src/agents/reporter/graph.py

### 工具系统

系统提供统一的工具获取函数 `get_tools_from_context(context)`，自动从上下文配置中组装工具列表：

```python
from src.agents.common.tools import get_tools_from_context

async def get_graph(self, **kwargs):
    context = self.get_context()
    tools = await get_tools_from_context(context)
    # tools 已包含：基础工具、知识库工具、MCP 工具
```

该函数会自动处理三类工具的组装：
1. **基础工具**: 从 `context.tools` 筛选的内置工具
2. **知识库工具**: 根据 `context.knowledges` 自动生成检索工具
3. **MCP 工具**: 根据 `context.mcps` 加载并过滤的 MCP 服务器工具

### BaseContext 配置字段

`BaseContext` 已内置以下常用配置字段，所有智能体可直接复用：

| 字段 | 类型 | 说明 |
|------|------|------|
| `model` | str | 使用的 LLM 模型 |
| `system_prompt` | str | 系统提示词 |
| `tools` | list[str] | 启用的内置工具列表 |
| `knowledges` | list[str] | 关联的知识库列表 |
| `mcps` | list[str] | 启用的 MCP 服务器名称 |

```python
from src.agents.common import BaseContext

@dataclass(kw_only=True)
class MyAgentContext(BaseContext):
    # 继承所有 BaseContext 字段
    # 可在此添加智能体特有的额外配置
    custom_field: str = "默认值"
```

如需自定义工具选项（如 ReporterAgent 的 MySQL 工具），可覆盖 `tools` 字段的 `options` 元数据：

```python
from src.agents.common import BaseContext, gen_tool_info
from src.agents.common.tools import get_buildin_tools
from src.agents.common.toolkits.mysql import get_mysql_tools

@dataclass(kw_only=True)
class ReporterContext(BaseContext):
    tools: Annotated[list[dict], {"__template_metadata__": {"kind": "tools"}}] = field(
        default_factory=lambda: [t.name for t in get_mysql_tools()],
        metadata={
            "name": "工具",
            "options": lambda: gen_tool_info(get_buildin_tools() + get_mysql_tools()),
            "description": "包含内置工具和 MySQL 工具包。",
        },
    )

    def __post_init__(self):
        self.mcps = ["mcp-server-chart"]  # 默认启用图表 MCP
```

智能体实例的生命周期交给管理器处理，会在自动发现时完成初始化并缓存单例，以便快速响应请求。在容器内热重载时，只要保存文件即可触发重新导入；需要强制刷新可调用 `agent_manager.get_agent(<id>, reload=True)`。

更多动态工具选择与 MCP 注册的例子，见 `src/agents/chatbot/graph.py` 中的中间件组合。

### 拓展现有智能体

智能体保持为 LangGraph 的标准节点组合，因此可以在原有 `graph.py` 中添加节点、条件与消息转换器。复用现成上下文时，只需扩展当前 `context_schema` 的字段；若功能差异较大，可以创建新的上下文类并替换 `context_schema`。

对工具、模型或提示语的调整建议封装到中间件或独立函数里，既方便多智能体共用，又能保持 `BaseAgent` 的基础接口稳定。变更提交后无需手动刷新注册表，只要确保包结构未改变，智能体会在热重载中自动更新。

### 子智能体与中间件

子智能体集中放在 `src/agents/common/subagents` 目录，典型例子是 `calc_agent`，它通过 LangChain 的 `create_agent` 构建计算器能力并以工具暴露给主图。新增子智能体时沿用这一结构：在目录内编写封装函数与 `@tool` 装饰器，导出后即可被任意智能体调用。

中间件位于 `src/agents/common/middlewares`，包含上下文感知提示词、模型选择、动态工具加载以及附件注入等实现。如果需要编写新的中间件，请遵循 LangChain 官方文档中对 `AgentMiddleware`、`ModelRequest`、`ModelResponse` 等接口的定义，完成后在该目录的 `__init__.py` 暴露入口，主智能体即可在 `middleware` 列表中引用。

#### 文件上传中间件

文件上传功能通过 `inject_attachment_context` 中间件实现（位于 `src/agents/common/middlewares/attachment_middleware.py`）。该中间件基于 LangChain 1.0 的 `AgentMiddleware` 标准实现，具有以下特点：

1. **状态扩展**：定义 `AttachmentState` 扩展 `AgentState`，添加可选的 `attachments` 字段
2. **自动注入**：在模型调用前，从 `request.state` 中读取附件并转换为 `SystemMessage`
3. **向后兼容**：不使用文件上传的智能体不受影响

##### 为智能体启用文件上传

只需两步：

**步骤 1：声明能力**（让前端显示上传按钮）

```python
class MyAgent(BaseAgent):
    capabilities = ["file_upload"]
```

**步骤 2：添加中间件**（让智能体能够处理附件内容）

```python
from src.agents.common.middlewares import inject_attachment_context

async def get_graph(self):
    graph = create_agent(
        model=load_chat_model("..."),
        tools=tools,
        middleware=[
            inject_attachment_context,  # 添加附件中间件
            context_aware_prompt,       # 其他中间件...
            # ...
        ],
        checkpointer=await self._get_checkpointer(),
    )
    return graph
```

##### 工作流程

1. **前端上传**：用户在聊天界面上传文档（txt、md、docx、html）
2. **API 解析**：后端将文档转换为 Markdown 格式并存储到数据库（超过 32k 会被截断）
3. **自动加载**：API 层在调用 agent 前从数据库加载附件数据
4. **中间件注入**：`inject_attachment_context` 自动将附件内容注入为系统消息
5. **模型处理**：LLM 接收到附件内容和用户问题，进行综合回答

这种设计确保了附件功能的可选性和可扩展性，任何智能体都可以通过添加中间件快速启用文件上传能力。

## 内置工具与 MCP 集成

系统会根据配置自动组装工具集合，涵盖知识图谱查询、向量检索生成的动态工具、MySQL 只读查询能力、Tavily 搜索以及所有注册的 MCP 工具。

MCP (Model Context Protocol) 服务的配置现已全面支持通过系统管理界面或 API 进行动态管理，数据持久化存储在数据库中。`src/services/mcp_service.py` 仅作为核心逻辑层和默认配置的存放处，不再建议直接修改代码来添加服务器。

### MCP 服务器管理

系统提供了完善的 API (`/system/mcp-servers`) 和管理界面来执行 MCP 服务器的增删改查操作。

#### 支持的传输协议

系统支持三种 MCP 传输协议：

1.  **SSE (Server-Sent Events)**: 标准的 HTTP SSE 连接
2.  **Streamable HTTP**: 支持流式传输的 HTTP 连接（远程）
3.  **Stdio**: 通过标准输入/输出运行本地进程（支持 Python/Node.js 等）

#### 配置示例

以下是通过管理界面添加 MCP 服务器时的常见配置参数示例（对应 API 请求体）：

##### 1. 远程 HTTP/SSE 服务器

*   **Server Name**: `sequentialthinking`
*   **Transport**: `streamable_http` (或 `sse`)
*   **URL**: `https://remote.mcpservers.org/sequentialthinking/mcp`

**特点**：
- 无需本地安装，适合公开可用的 MCP 服务
- 启动速度快，无需本地依赖

##### 2. 使用 npx 运行 Node.js 包

*   **Server Name**: `mcp-server-chart`
*   **Transport**: `stdio`
*   **Command**: `npx`
*   **Args**: `["-y", "@antv/mcp-server-chart"]`

**特点**：
- 自动下载并运行 Node.js 包
- 适合 Node.js 生态的 MCP 服务

##### 3. 使用 uvx 运行 Python 包

*   **Server Name**: `mysql-mcp-server`
*   **Transport**: `stdio`
*   **Command**: `uvx`
*   **Args**: `["mysql_mcp_server"]`
*   **Environment Variables**:
    ```json
    {
        "MYSQL_DATABASE": "your_database",
        "MYSQL_HOST": "localhost",
        "MYSQL_PASSWORD": "your_password",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "your_username"
    }
    ```

**特点**：
- 自动管理 Python 虚拟环境和依赖
- 适合 PyPI 上已发布的 MCP 服务

##### 4. 使用 uv 运行本地仓库

*   **Server Name**: `arxiv-mcp-server`
*   **Transport**: `stdio`
*   **Command**: `uv`
*   **Args**:
    ```json
    [
        "tool",
        "run",
        "arxiv-mcp-server",
        "--storage-path", "src/agents/mcp_repos/arxiv-mcp-server"
    ]
    ```

**特点**：
- 直接运行本地 git 仓库中的 MCP 服务
- 支持热重载，适合开发调试

### 动态工具加载与管理

系统提供统一的 MCP 服务层 (`src/services/mcp_service.py`) 封装所有 MCP 相关操作。

#### 1. 智能体获取工具

智能体开发时，应使用 `get_enabled_mcp_tools()` 获取工具。该函数会自动根据数据库中的配置，过滤掉被禁用的工具。

```python
from src.services.mcp_service import get_enabled_mcp_tools

# 获取指定服务器的工具（自动过滤掉在管理界面禁用的工具）
tools = await get_enabled_mcp_tools("sequentialthinking")
```

#### 2. 工具粒度控制

通过管理界面或 API (`PUT /system/mcp-servers/{name}/tools/{tool_name}/toggle`)，管理员可以启用或禁用特定的 MCP 工具。禁用后的工具不会出现在 `get_enabled_mcp_tools` 的返回列表中，从而防止智能体调用不需要的能力。

#### 3. 默认服务器配置

系统首次启动时，会加载 `src/services/mcp_service.py` 中 `_DEFAULT_MCP_SERVERS` 定义的默认服务器（如 `sequentialthinking` 和 `mcp-server-chart`）到数据库中。后续的修改将以数据库为准。

### MySQL 数据库

在 数据库报表助手（SqlReporterAgent） 中，可以通过配置下面环境变量，让 Agent 能够连接到 MySQL 数据库。并通过执行 SQL 查询，获取数据库中的数据。

设置数据库连接时，在 `.env` 中提供以下字段：

```env
MYSQL_HOST=192.168.1.100
MYSQL_USER=username
MYSQL_PASSWORD=your_secure_password
MYSQL_DATABASE=database_name
MYSQL_DATABASE_DESCRIPTION=业务主库（可选提示）
MYSQL_PORT=3306
MYSQL_CHARSET=utf8mb4
```

所有查询限定在只读范围（SELECT、SHOW、DESCRIBE、EXPLAIN），请求会经过表名校验与超时控制，默认限制 60 秒与 100 行输出，并可通过配置调整上限。连接信息会反馈给 LangGraph，智能体可以自动陈述数据库用途并选择更准确的检索策略。详见代码部分 `src/agents/common/toolkits/mysql/`

### 多模态图片支持

系统支持接收图片作为输入，与文本结合形成多模态查询。图片支持的核心特性如下：

#### 1. 图片上传与处理
- 通过 `/chat/image/upload` 接口上传图片
- 自动处理图片格式转换和压缩
- 返回 base64 编码的图片数据
- 图片大小限制为 10MB
- 支持的图片格式：JPEG、PNG、WebP、GIF、BMP
- 自动压缩超过 5MB 的图片

当发送包含图片的请求时，消息格式为：
```json
{
  "query": "这张图片里有什么？",
  "image_content": "<base64编码的图片数据>",
  "config": {},
  "meta": {}
}
```

智能体会自动识别多模态消息并将其传递给支持图片的模型。如果模型不支持图片，会自动忽略图片内容，只处理文本部分。系统会将图片转换为符合模型要求的格式（通常是 base64 编码的 JPEG 或 PNG），确保与主流多模态模型兼容。

目前仅支持上传单个图片，图片以 base64 编码形式存储在数据库。系统会自动处理图片的格式转换和压缩，并生成缩略图以优化性能。

### 图片上传响应格式

```json
{
  "success": true,
  "image_content": "<base64编码的原始图片数据>",
  "thumbnail_content": "<base64编码的缩略图数据>",
  "width": 1024,
  "height": 768,
  "format": "JPEG",
  "mime_type": "image/jpeg"
}
```

系统会将图片信息与用户查询一同传递给支持多模态的模型，并自动适配模型要求的格式。
