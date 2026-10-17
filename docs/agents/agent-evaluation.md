# 评估智能体

本页说明 Agent 评估的接入边界。npm CLI `@xerrors/yuxi` 的当前命令面向认证、Agent 目录、Public Thread 对话、消息附件和知识库只读查询，没有 `yuxi agent eval` 或 Langfuse Dataset experiment 命令。使用方法见[CLI 教程](../intro/cli.md)，命令以[CLI 实现](https://github.com/xerrors/Yuxi/blob/main/packages/yuxi-cli/src/cli.ts)为准。

知识库检索评估仍见[知识库评估](../intro/evaluation.md)。如果需要构建自定义 Agent 评估器，应直接使用[智能体 Public API](../advanced/agents-public-api.md)创建 Thread、提交 Input、观察事件并回读 Turn 结果；评估脚本需要自行拥有 Dataset、并发、超时、评分和结果存储语义。

Langfuse tracing 是 API/worker 的观测能力，不代表 npm CLI 支持 Dataset experiment。相关配置与服务端观测边界见[Langfuse 集成](../advanced/langfuse-integration.md)。
