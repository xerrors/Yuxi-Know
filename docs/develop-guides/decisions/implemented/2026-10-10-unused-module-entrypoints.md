# 收窄无消费者的模块入口

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/runtime/__init__.py

## 问题

runtime 包重导出多个不同域的函数，空 chatbot main 伪装可运行入口，后台作业 repository 存在无调用且无限量的 list_all。审计仅搜索生产代码会遗漏文档化的 Agent 扩展接口。

## 决策

### 实现方案

保留开发文档引用的 BaseAgent、BaseContext、load_chat_model 导出。内建 chatbot 和性能探针从实际 base Owner 导入。删除无源码/测试/文档消费者的 BaseState、resolve_chat_model_spec、get_tool_info、get_enabled_mcp_tools 包重导出；模型解析、状态及 MCP 的对应实现保持原处；未消费的工具信息旧实现由[模块死代码清理](./2026-10-12-dead-code-cleanup.md)删除。删除空 main 和后台作业 list_all，保留实际使用的有界 list 与 summarize。

## 替代方案

清空 runtime 所有导出会破坏文档化扩展接口。删除全部名为 list_all 的方法会误删 Skill 真实消费者。保留空入口增加导航歧义。

## 验证

全仓源码、测试、配置与文档搜索确认两个 BaseAgent 内部消费者及三项文档化导出；注册与发现没有使用空 main。BackgroundJobRepository 实际消费者使用有界 list、summarize 和专用查询；Skill repository 的 list_all 保留。既有全量后端 unit 覆盖内建发现、运行时和作业 service；不添加仅镜像删除结果的测试。

旧能力不存在：最终源码不含空 chatbot main、BackgroundJobRepository.list_all 和四个无消费者重导出。

重新引入条件：有明确消费者及用途时，在真实 Owner 上设计入口，不恢复空函数或无限量查询。

## 后果

未文档化的包导出使用者需要改为实际模块导入；当前仓库、文档、配置与注册无此消费证据。没有持久化或网络协议变化。
