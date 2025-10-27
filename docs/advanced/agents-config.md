# 智能体

## 智能体开发

系统基于 [LangGraph](https://github.com/langchain-ai/langgraph) 框架，支持自定义智能体应用开发。

系统默认集成示例智能体：

| 智能体 | 功能 | 位置 |
|--------|------|------|
| **基础智能体** | 对话功能 | `src/agents/chatbot/` |
| **ReAct 智能体** | 推理与行动循环 | `src/agents/react/` |

### 开发自定义智能体

如果需要开发自己的智能体的话，可以基于智能体基类以及相关脚手架实现。整体上是和 LangGraph 的架构是适配的，只是在部分功能上需要和平台更加适配才好。

#### 1. 创建智能体类

继承 `BaseAgent` 并实现 `get_graph` 方法：

```python
from .base import BaseAgent

class CustomAgent(BaseAgent):
    def get_graph(self):
        # 返回 LangGraph 实例
        return graph_instance

    @property
    def context_schema(self):
        # 定义配置参数
        return schema
```

#### 2. 注册智能体

在 `src/agents/__init__.py` 中注册：

```python
from .custom_agent import CustomAgent

agent_manager = AgentManager()
agent_manager.register_agent(CustomAgent)
agent_manager.init_all_agents()
```

#### 3. 参考示例

查看 `src/agents/react/graph.py` 中的 `ReActAgent` 实现示例。

## 内置工具与 MCP 集成

系统默认会为对话/推理智能体注册一组“内置工具”，并根据配置动态启用：

- 知识图谱查询：`query_knowledge_graph`
  - 依赖 Neo4j 服务（见 docker-compose 中 `graph`）
  - 返回包含三元组的结果，适合图谱关系类问题
- 网页搜索：`TavilySearch`
  - 需要设置 `TAVILY_API_KEY` 才会启用
  - LLM 在需要时自动调用，提供实时网页信息
- 知识库检索工具：按知识库动态生成
  - 工具名称形如 `query_<db_id前缀>`；描述来自知识库名称与说明
  - 在工具选择阶段，用描述帮助模型做针对性检索
- MySQL 工具包：只读查询
  - `mysql_list_tables`、`mysql_describe_table`、`mysql_query`
  - 环境变量见下，具备超时/行数限制与注入防护

MCP（Model Context Protocol）可接入外部可视化或其他工具能力：
- 在 `src/agents/common/mcp.py` 的 `MCP_SERVERS` 添加配置；`transport` 字段名必须正确
- 常见问题：无法列出工具多因服务不可达或配置错误；优先检查可达性与字段名


### 1. MySQL 数据库集成

系统支持智能体查询 MySQL 数据库，为数据分析提供强大支持。

### 配置数据库连接

在环境变量中配置数据库信息：

```env
# MySQL 数据库配置
MYSQL_HOST=192.168.1.100
MYSQL_USER=username
MYSQL_PASSWORD=your_secure_password
MYSQL_DATABASE=database_name
MYSQL_PORT=3306
MYSQL_CHARSET=utf8mb4
```

在智能体配置中启用以下 MySQL 工具：

| 工具名称 | 功能描述 |
|----------|----------|
| `mysql_list_tables` | 获取数据库中的所有表名 |
| `mysql_describe_table` | 获取指定表的详细结构信息 |
| `mysql_query` | 执行只读的 SQL 查询语句 |

### 安全特性

- ✅ **只读操作**: 仅允许 SELECT、SHOW、DESCRIBE、EXPLAIN 操作
- ✅ **SQL 注入防护**: 严格的表名参数验证
- ✅ **超时控制**: 默认 60 秒，最大 600 秒
- ✅ **结果限制**: 默认 10000 字符，100 行，最大 1000 行

### 可视化图表-MCP-Server

系统支持基于 MCP（Model Context Protocol）的图表可视化功能。

- 基于 @antvis 团队开发的 [可视化图表-MCP-Server](https://www.modelscope.cn/mcp/servers/@antvis/mcp-server-chart)
- 支持多种图表类型和数据可视化
- 通过魔搭社区配置 Host 资源

在 `src/agents/common/mcp.py` 的 `MCP_SERVERS` 中添加配置：

```python
# MCP Server configurations
MCP_SERVERS = {
    "sequentialthinking": {
        "url": "https://remote.mcpservers.org/sequentialthinking/mcp",
        "transport": "streamable_http",
    },
    "mcp-server-chart": {
        "url": "https://mcp.api-inference.modelscope.net/9993ae42524c4c/mcp",
        "transport": "streamable_http",
    }
}
```

::: warning 配置注意
记得将 `type` 字段修改为 `transport`，并确保服务可达。
:::
