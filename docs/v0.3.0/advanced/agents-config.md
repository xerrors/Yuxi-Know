# 智能体

## 智能体开发

系统基于 [LangGraph](https://github.com/langchain-ai/langgraph) 并通过统一的 `AgentManager` 管理所有智能体。`src/agents/__init__.py` 会在启动时遍历 `src/agents` 目录，对每个包含 `__init__.py` 的子包执行自动发现：所有继承 `BaseAgent` 的类都会被注册并立即初始化，因此只要代码落位正确，就不需要再手动登记或修改管理器。

仓库预置了若干可直接运行的智能体：`chatbot` 聚焦对话与动态工具调度，`mini_agent` 提供精简模板，`reporter` 演示报告类链路。这些目录展示了上下文类、Graph 构造方式、子智能体引用以及中间件组合的范例，新增功能时可以直接复用。

### 创建新的智能体

在 `src/agents` 下新建一个包，保持与现有目录一致的结构：放置 Graph 构造逻辑（通常命名为 `graph.py`），并在包内的 `__init__.py` 中暴露主类。

智能体类必须继承 `src.agents.common.BaseAgent`，同时实现异步的 `get_graph` 方法来返回编译后的 LangGraph 实例，并配置好 `checkpointer`，否则无法从历史对话中恢复。

需要额外上下文字段时，可继承 `BaseContext` 构建自己的配置表单，再把类绑定到 `context_schema`，平台会在 `saves/agents/<module>` 下生成默认配置。

案例1 使用内置工具构建一个极简的智能体，可以动态选择 Prompt 和 LLM：

<<< @/../src/agents/mini_agent/graph.py

案例2 基于MySQL工具，以及自定义 MCP Server 的数据库报表助手。

<<< @/../src/agents/reporter/graph.py



智能体实例的生命周期交给管理器处理，会在自动发现时完成初始化并缓存单例，以便快速响应请求。在容器内热重载时，只要保存文件即可触发重新导入；需要强制刷新可调用 `agent_manager.get_agent(<id>, reload=True)`。

更多动态工具选择与 MCP 注册的例子，见 `src/agents/chatbot/graph.py` 中的中间件组合。

### 拓展现有智能体

智能体保持为 LangGraph 的标准节点组合，因此可以在原有 `graph.py` 中添加节点、条件与消息转换器。复用现成上下文时，只需扩展当前 `context_schema` 的字段；若功能差异较大，可以创建新的上下文类并替换 `context_schema`。

对工具、模型或提示语的调整建议封装到中间件或独立函数里，既方便多智能体共用，又能保持 `BaseAgent` 的基础接口稳定。变更提交后无需手动刷新注册表，只要确保包结构未改变，智能体会在热重载中自动更新。

### 子智能体与中间件

子智能体集中放在 `src/agents/common/subagents` 目录，典型例子是 `calc_agent`，它通过 LangChain 的 `create_agent` 构建计算器能力并以工具暴露给主图。新增子智能体时沿用这一结构：在目录内编写封装函数与 `@tool` 装饰器，导出后即可被任意智能体调用。

中间件位于 `src/agents/common/middlewares`，包含上下文感知提示词、模型选择以及动态工具加载等实现。如果需要编写新的中间件，请遵循 LangChain 官方文档中对 `AgentMiddleware`、`ModelRequest`、`ModelResponse` 等接口的定义，完成后在该目录的 `__init__.py` 暴露入口，主智能体即可在 `middleware` 列表中引用。

## 内置工具与 MCP 集成

系统会根据配置自动组装工具集合，涵盖知识图谱查询、向量检索生成的动态工具、MySQL 只读查询能力、Tavily 搜索以及所有注册的 MCP 工具。

工具的启用状态和描述由配置文件或环境变量决定，当依赖缺失时会被中间件自动忽略，从而避免在图中加载不可用能力。MCP Server 的接入方式保持不变，只需在 `src/agents/common/mcp.py` 的 `MCP_SERVERS` 中填入服务地址与 `transport` 类型，如需更多范式可参阅 LangChain 官方文档。

### MySQL 数据库

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

所有查询限定在只读范围（SELECT、SHOW、DESCRIBE、EXPLAIN），请求会经过表名校验与超时控制，默认限制 60 秒与 100 行输出，并可通过配置调整上限。连接信息会反馈给 LangGraph，智能体可以自动陈述数据库用途并选择更准确的检索策略。
