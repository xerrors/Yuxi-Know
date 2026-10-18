# 移除智能体待办中间件

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/runtime/agent_backends/chatbot/graph.py

## 问题

待办工具让已生成完整回答的智能体继续更新内部清单，随后产生无法独立回答问题的收尾消息。用户明确要求移除这项能力。

## 决策

### 实现方案

从 ChatbotAgent 装配中移除待办中间件和专用提示词；状态提取与响应类型不再发布待办字段。前端删除待办状态区、工具专用渲染器及其事件传递。研究角色和内置 Skill 使用文字规划与现有协作会话组织任务。文件、上下文用量、交付物和协作人工操作入口继续由各自现有组件拥有。

持久消息和 checkpoint 保留历史事实；历史工具调用沿用通用工具展示。知识库文件搜索只增强工具描述：指定库时显式传递 kb_id，跨库搜索继续遵循现有权限与输入契约。检索去重、引用预算、thinking 协议和行号不在本实现范围内。

## 替代方案

保留待办工具并仅要求模型调整调用顺序，不能满足用户要求的完整移除。仅删除后端装配会留下失效的状态、前端和 Skill 接口。

## 验证

旧能力不存在：新建与 checkpoint 清理图均不注册待办工具或 channel，状态响应与当前前端不发布待办能力，内置研究指引不再调用该工具。

重新引入条件：出现明确用户需求，重新定义工具、持久状态、展示和最终回答的边界，并提供独立验证。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 新建和清理图均无待办工具与 channel | 只删除提示词仍注册工具 | ChatbotAgent 装配 | `test_chatbot_tool_surface.py` 的真实 LangGraph 构图；相关后端 85 项通过 | 恢复中间件后两个构图用例均失败 | Passed |
| 历史待办字段不再进入状态响应 | 旧 checkpoint 泄漏已移除字段 | execution.extract_agent_state | checkpoint unit 与真实 HTTP / PostgreSQL integration 2 项通过 | 含历史待办字段的 checkpoint 只返回当前白名单，跨用户读取仍拒绝 | Passed |
| 前端保留上下文与状态入口 | 删除共享入口导致其他能力失效 | SessionWorkspace 与工具渲染 | frontend lint、706 项 unit、build 通过；真实浏览器注入历史待办字段核验状态面板 | 历史状态不能重新显示待办区，上下文用量仍可见 | Passed |

后端完整非 slow 单测 2,838 项通过、97 项环境相关跳过；跳过项不计为通过。HTTP 用例使用独立 API 进程、自建会话和真实 PostgreSQL checkpoint；空会话未执行工具或写入文件，清理只移除自建会话关联记录，Workspace 目录由用户 Project 持有。

## 后果

已有自定义提示词可能仍要求使用已移除工具；保留用户配置和历史数据，不静默改写。API、worker 与内置 Skill 投影的生效时点由正常部署与初始化负责。真实模型的收尾质量未复测，本决定的证据证明能力移除，不证明模型回答质量。
