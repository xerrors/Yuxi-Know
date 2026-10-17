# 机制详解

本组页面面向已经了解基本部署和使用方式的开发者、运维人员，解释运行状态、事实归属、权限及失败恢复。首次完成产品任务从[快速开始](../intro/quick-start.md)进入；部署和参数查找使用[部署参考](../advanced/deployment.md)与[配置参考](../advanced/configuration.md)。

## 怎么读

- 排查资源不可见、共享授权或运行中撤权：看[资源权限](./resource-permissions.md)。
- 理解配置怎样进入一次运行：看[Agent 运行时上下文](./agent-runtime.md)。
- 核对排队、引导、取消或恢复：看[输入队列与调度](./agent-request-queue.md)。
- 排查文件路径、执行环境和清理：看[沙盒与文件系统](./sandbox.md)。
- 理解长对话怎样压缩：看[上下文压缩](./context-compression.md)。
- 排查文档解析、入库和检索：看[知识库](./knowledge-base.md)。

每页都按“入口 → 装配或派发 → 执行 Owner → 持久化/文件 → 可观察结果”展开。排查问题时先看“失败、恢复与观察边界”，修改实现时从“源码定位与验证”进入 owning 模块和测试。

## 专题地图

| 专题 | 回答的问题 | 配置/操作入口 |
| --- | --- | --- |
| [资源权限](./resource-permissions.md) | 角色、私有/共享范围和运行中撤权在哪里执行？ | [配置智能体](../agents/agents-config.md#私有与共享定义)、[API Key 接入](../advanced/api-key-integration.md) |
| [Agent 运行时上下文](./agent-runtime.md) | 配置、权限、文件和 checkpoint 怎样组成一次运行？ | [配置和开发智能体](../agents/agents-config.md) |
| [输入队列与调度](./agent-request-queue.md) | Input 怎样消费成 Turn/Run，steer、取消和失败后怎样恢复？ | [Agents Public API](../advanced/agents-public-api.md)、[会话协作](../agents/session-cooperation.md) |
| [沙盒与文件系统](./sandbox.md) | runtime identity、挂载、路径权限和回收怎样协作？ | [沙盒配置与运维](../advanced/sandbox-operations.md) |
| [上下文压缩](./context-compression.md) | 单一阈值怎样控制工具结果压缩、摘要和主动压缩？ | [中间件](../agents/middleware.md)、[智能体配置](../agents/agents-config.md) |
| [知识库](./knowledge-base.md) | 文件状态、存储、权限和 Agent 检索怎样连接？ | [知识库教程](../intro/knowledge-base.md)、[文档处理](../advanced/document-processing.md) |

只有当主题有稳定的 Owner、真实 consumer 和可验证链路时，才新增机制页。未来设计放入 roadmap 或 proposed decision，不画进当前运行图。
