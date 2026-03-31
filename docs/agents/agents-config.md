# 智能体配置

Yuxi 的智能体系统基于 LangGraph 构建。对开发者来说，最重要的不是单独理解某个页面或某个字段，而是理解三件事：

- Agent 如何被定义和发现
- Context 如何驱动配置界面
- Context 如何贯穿一次 Agent 运行周期

本文聚焦这三部分。

## 1. 整体结构

智能体开发围绕四个核心对象展开：

- **`BaseAgent`**：统一的 Agent 抽象，定义 `get_graph()`、`context_schema`、`capabilities`
- **`BaseContext`**：配置 Schema，也是前端配置项的来源
- **Graph / Middleware**：LangGraph 图与中间件链，决定运行时行为
- **AgentConfig**：数据库中的配置实例，前端侧边栏编辑的就是它

仓库中已经内置了可直接参考的智能体：

- `chatbot`：通用对话智能体
- `deep_agent`：深度分析智能体

## 2. Agent 的代码组织

建议在 `backend/package/yuxi/agents` 下按包组织一个智能体：

```text
backend/package/yuxi/agents/
└── my_agent/
    ├── __init__.py
    ├── context.py
    └── graph.py
```

最小实现通常包含：

- 一个继承 `BaseAgent` 的主类
- 一个 `context_schema`
- 一个 `get_graph()` 实现

示例：

```python
from yuxi.agents import BaseAgent, BaseContext, load_chat_model
from langchain.agents import create_agent


class MyAgent(BaseAgent):
    name = "我的智能体"
    description = "示例智能体"
    context_schema = BaseContext

    async def get_graph(self, context=None, **kwargs):
        context = context or self.context_schema()
        graph = create_agent(
            model=load_chat_model(context.model),
            system_prompt=context.system_prompt,
            checkpointer=await self._get_checkpointer(),
        )
        return graph
```

## 3. Context 是配置模型，不只是运行时参数

### 3.1 `BaseContext` 的角色

`BaseContext` 定义在 `backend/package/yuxi/agents/context.py`，它不是一个普通的数据类，而是整个智能体配置链路的核心：

- 它定义了 Agent 可以配置哪些字段
- 它定义了这些字段在前端如何展示
- 它也是运行期传入 Graph 和中间件的上下文对象

当前基础字段包括：

| 字段 | 作用 |
| --- | --- |
| `system_prompt` | 系统提示词 |
| `model` | 主模型 |
| `tools` | 启用的内置工具 |
| `knowledges` | 关联知识库 |
| `mcps` | 启用的 MCP 服务器 |
| `skills` | 关联 Skills |
| `subagents_model` | 子智能体默认模型 |
| `subagents` | 启用的子智能体 |
| `summary_threshold` | 摘要触发阈值 |
| `thread_id` / `user_id` | 运行期标识，不作为页面配置项暴露 |

### 3.2 前端配置项如何从 Context 生成

`BaseContext.get_configurable_items()` 会遍历字段定义，把字段类型、默认值、描述、模板元数据整理成 `configurable_items`。

随后：

1. `BaseAgent.get_info()` 暴露 `configurable_items`
2. 前端读取 Agent 详情
3. `AgentConfigSidebar` 按 `template_metadata.kind` 渲染不同控件

也就是说，`AgentConfigSidebar` 不是手写每个字段，而是直接消费 `context_schema` 生成的配置描述。

这也是为什么：

- 新增一个 Context 字段，往往会直接影响侧边栏
- 字段的 `metadata`、`Annotated` 类型信息，会直接影响展示方式

### 3.3 `AgentConfigSidebar` 与 AgentConfig 的联动关系

这部分是最关键的。

在前端：

- `AgentConfigSidebar.vue` 负责渲染配置表单
- `agentStore` 加载配置时，读取 `config_json.context`
- 如果某些字段未配置，会用 `configurable_items` 中的默认值补全
- 保存时，前端将当前表单写回 `config_json: { context: agentConfig }`

因此真实关系是：

```text
context_schema
  -> get_configurable_items()
  -> Agent detail API 返回 configurable_items
  -> AgentConfigSidebar 渲染表单
  -> 用户编辑后保存到 config_json.context
```

这里需要特别注意两点：

- **侧边栏展示结构来自 `context_schema`**
- **配置实例值来自数据库中的 `config_json.context`**

前者决定“能配什么、怎么展示”，后者决定“当前配置实际选了什么”。

### 3.4 自定义 Context 的推荐方式

如果某个智能体有额外配置，不要在前端单独加一套表单，而是直接扩展 Context：

```python
from dataclasses import dataclass, field
from yuxi.agents import BaseContext


@dataclass(kw_only=True)
class MyAgentContext(BaseContext):
    custom_mode: str = field(
        default="default",
        metadata={
            "name": "运行模式",
            "description": "控制智能体的自定义行为",
            "options": ["default", "strict"],
        },
    )
```

然后在 Agent 中声明：

```python
class MyAgent(BaseAgent):
    context_schema = MyAgentContext
```

这会同时影响：

- 后端可接收的配置结构
- 前端配置侧边栏的展示内容
- 运行期 `context` 可访问的字段

## 4. Context 如何贯穿 Agent 的运行周期

Context 的价值不只在“配置页面”。它贯穿了从配置加载到实际执行的整条链路。

### 4.1 配置加载阶段

在聊天请求进入后端时，服务会先解析 `agent_config_id`，再加载对应配置。

当前主流程在 `chat_service.py` 中：

1. 通过 `agent_config_id` 查找配置
2. 读取该配置绑定的 `agent_id`
3. 取出 `config_json.context`
4. 与 `user_id`、`thread_id` 合并成运行时输入

也就是说，运行期 Context 的基础来源并不是前端临时状态，而是数据库中保存的 AgentConfig。

### 4.2 Context 实例化阶段

`BaseAgent` 在运行前会创建 `context_schema()` 实例，并通过 `update_from_dict()` 注入配置值。

这一步完成后，Context 才真正成为运行期对象。

可以把它理解为：

```text
config_json.context + runtime ids -> context_schema instance
```

### 4.3 Graph 构建阶段

`get_graph(context=context)` 会收到这份 Context。

以内置 `chatbot` 为例，Context 会直接参与：

- 主模型选择：`context.model`
- 系统提示词拼接：`context.system_prompt`
- 子智能体默认模型：`context.subagents_model`
- 子智能体列表：`context.subagents`
- 摘要阈值：`context.summary_threshold`

因此 Graph 不是和 Context 解耦的。相反，Graph 的构造本身就依赖 Context。

### 4.4 中间件运行阶段

中间件通过 `request.runtime.context` 或 `runtime.context` 继续读取和修改 Context。

例如：

- `RuntimeConfigMiddleware`
  - 读取 `model`、`system_prompt`、`tools`、`mcps`
  - 动态覆盖模型、系统提示词和工具列表
- `SkillsMiddleware`
  - 读取 `skills`
  - 计算可见技能闭包
  - 将 skills 提示段注入 `system_prompt`
  - 在运行期回写 `_visible_skills`
- 文件系统与沙盒接入
  - 通过 `thread_id` 获取对应沙盒
  - 通过 `skills` 决定 `/home/gem/skills` 的可见范围

所以 Context 既是输入配置，也是中间件共享的运行时状态载体。

### 4.5 文件系统与 Viewer 阶段

文件系统服务不会重新发明一套配置结构，而是再次从 `config_json.context` 还原出 runtime context，用于：

- 判断当前线程下 Agent 可见的 Skills
- 构造 Agent 视图的 composite backend
- 构造 Viewer 视图的文件系统展示

这也是为什么 Context 不只是聊天链路的一部分，它还影响：

- Agent 文件工具
- Viewer 文件浏览器
- Skills 可见性
- 沙盒挂载语义

### 4.6 恢复运行阶段

在 `resume` 流程中，系统同样会重新加载 AgentConfig，并重新构造 Context，再继续执行 Graph。

也就是说，无论是：

- 首次对话
- 中断恢复
- 文件系统查看

它们都依赖同一份 Context 配置来源。

## 5. `capabilities` 的作用

`capabilities` 用于声明前端可直接从 Agent 静态元数据判断的能力开关，控制上传入口、文件面板等固定 UI，不等同于 Context，也不适合表达运行中才会出现的状态。

示例：

```python
class MyAgent(BaseAgent):
    capabilities = ["file_upload", "files"]
```

当前常见能力包括：

| capability | 说明 |
| --- | --- |
| `file_upload` | 启用上传入口 |
| `files` | 启用文件面板 |

像 todo 这类运行态信息，不建议再放进 `capabilities`。Yuxi 当前会直接从 LangGraph state 中提取 `agent_state.todos`，前端按运行时是否真的存在任务来决定是否展示待办入口与状态卡片。

它解决的是“Agent 先天支持什么固定入口”，而不是“运行时当前产生了什么状态”。

## 6. 开发建议

### 6.1 新增配置时优先改 Context

如果一个配置项会影响 Agent 行为，优先考虑把它做成 `context_schema` 字段，而不是前端单独维护状态。

### 6.2 把 Graph 逻辑和配置逻辑分开

推荐做法：

- `context.py` 定义配置模型
- `graph.py` 使用这些配置构建 Graph

这样前后端联动关系会清晰很多。

### 6.3 把“配置来源”和“运行时状态”区分开

建议始终区分两层语义：

- `config_json.context`：持久化配置来源
- `runtime.context`：实际运行对象，可能被中间件继续补充或修改

## 7. 相关主题

- [工具系统](./tools-system.md)
- [中间件](./middleware.md)
- [沙盒架构与设计](./sandbox-architecture.md)
- [MCP 集成](./mcp-integration.md)
- [Skills 管理](./skills-management.md)
- [SubAgents 管理](./subagents-management.md)
