# 工具系统

Yuxi 的工具系统基于注册机制，支持多种工具类型的动态组装。

## 工具注册机制

Yuxi 的工具系统采用 `@tool` 装饰器注册机制，核心位于 `backend/package/yuxi/agents/toolkits/registry.py`。

### @tool 装饰器

```python
from yuxi.agents.toolkits.registry import tool

@tool(category="buildin", tags=["计算"], display_name="计算器")
def calculator(a: float, b: float, operation: str) -> float:
    """计算器：对给定的2个数字进行基本数学运算"""
    ...
```

装饰器参数：
- **category**: 工具分类，用于分组（`buildin`、`mysql`、`debug`）
- **tags**: 标签列表，用于前端展示
- **display_name**: 显示名称（给人看的名字）
- **icon**: 图标名称（可选）

### 自动发现

导入 `toolkits` 包时会自动触发注册：

```python
from yuxi.agents.toolkits import buildin, mysql  # 触发 @tool 装饰器执行
```

`toolkits/__init__.py` 中已包含 `buildin`、`mysql`、`debug` 模块的导入，这些模块加载时会自动注册所有带 `@tool` 装饰器的函数。

## 工具分类

### 内置工具 (buildin)

| 工具 | 说明 |
|------|------|
| `calculator` | 计算器，支持加减乘除 |
| `ask_user_question` | 向用户发起交互式提问 |
| `query_knowledge_graph` | 查询知识图谱三元组 |
| `text_to_img_qwen_image` | 使用 Qwen-Image 生成图片 |
| `tavily_search` | Tavily 网页搜索（需配置 `TAVILY_API_KEY`） |

### MySQL 工具 (mysql)

| 工具 | 说明 |
|------|------|
| `mysql_list_tables` | 列出数据库中所有表 |
| `mysql_describe_table` | 获取表结构信息 |
| `mysql_query` | 执行只读 SQL 查询 |

### 知识库工具 (kbs)

知识库工具通过 `get_common_kb_tools()` 获取，不通过 `@tool` 装饰器注册：

```python
from yuxi.agents.toolkits.kbs import get_common_kb_tools

kb_tools = get_common_kb_tools()
# 返回: [list_kbs, get_mindmap, query_kb]
```

| 工具 | 说明 |
|------|------|
| `list_kbs` | 列出用户可访问的知识库 |
| `get_mindmap` | 获取知识库的思维导图结构 |
| `query_kb` | 在指定知识库中检索内容 |

## 工具组装

工具组装在 `RuntimeConfigMiddleware` 中完成。根据上下文配置筛选工具：

1. **基础工具**：从 `context.tools` 中按名称筛选
2. **MCP 工具**：根据 `context.mcps` 加载 MCP 服务器工具
3. **知识库工具**：由 `KnowledgeBaseMiddleware` 独立处理

```python
# 中间件中的工具筛选逻辑
async def get_tools_from_context(self, context) -> list:
    selected_tools = []

    # 1. 基础工具
    for tool_name in context.tools or []:
        if tool_name in tools_map:
            selected_tools.append(tools_map[tool_name])

    # 2. MCP 工具
    for server_name in context.mcps or []:
        mcp_tools = await get_enabled_mcp_tools(server_name)
        selected_tools.extend(mcp_tools)

    return selected_tools
```

## Skills 集成

Skills 与工具是两种不同的扩展机制。工具是具体的功能实现，而 Skills 是包含提示词、工具依赖和元数据的完整技能包。通过 `context.skills` 配置 Skills 时，对应的技能文件会被挂载到 `/skills/<slug>/...`，智能体可以通过读取 SKILL.md 来了解如何使用这些技能。

关于 Skills 的详细机制，请参阅 [Skills 管理](./skills-management.md)。
