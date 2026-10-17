# 接入 Langfuse

Langfuse 是 Yuxi 的可选观测服务。它把一个 Turn 中各段 Run 的模型调用、工具调用、耗时和错误放到同一条 Trace 中，方便按用户、线程、智能体和轮次排查问题。

Langfuse 不拥有 Yuxi 的消息、运行状态或最终结果。即使 Langfuse 未配置、初始化失败或暂时不可用，聊天和 AgentRun 仍按本地业务链路运行。

## 能看到什么

Yuxi 会把本地运行信息映射到 Langfuse：

| Yuxi 信息 | Langfuse 字段 | 用途 |
| --- | --- | --- |
| 用户 `uid` | `user_id` | 按用户筛选 |
| 对话 `thread_id` | `session_id` | 查看同一线程的多轮运行 |
| 一轮工作 `turn_id` | Trace 与 `agent.turn` 根 Observation | 查看完整轮次，包含等待和恢复 |
| 一段执行 `run_id` | Run Observation | 查看该执行段的模型、工具、耗时和错误 |
| `agent_id`、operation 等 | metadata / tags | 按智能体和调用类型筛选 |

对话中的助手消息支持点赞或点踩，反馈保存在 PostgreSQL。平台超级管理员可从[集中反馈](./agent-feedback.md)打开反馈所属 Turn 的 Trace 复盘。

## 配置

在 API 和 worker 的运行环境中设置：

```bash
LANGFUSE_PUBLIC_KEY=<your-public-key>
LANGFUSE_SECRET_KEY=<your-secret-key>
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

`LANGFUSE_BASE_URL` 用于自托管或指定区域；留空时使用 SDK 默认地址。需要显式关闭时设置：

```bash
LANGFUSE_ENABLED=false
```

`LANGFUSE_ENABLED` 不填写时默认开启，但只有同时提供公钥、密钥且安装了 Langfuse SDK，实际 tracing 才会启用。修改环境变量后重新创建 API 和 worker 容器；如果修改了依赖，还要重新构建镜像：

```bash
docker compose up -d --force-recreate api worker
```

密钥只放在受保护的运行环境中，不要写入仓库、Agent 环境或公开日志。

## 验证是否生效

1. 重新创建读取了新配置的 API 和 worker，确认 `/api/system/ready` 已恢复。
2. 用测试账号发起一次真实对话，记录线程和大致时间。
3. 在 Langfuse 控制台按 `session_id`、`agent_id` 或时间筛选 trace。
4. 核对 trace 中的模型调用、工具调用、metadata 和耗时。
5. 对助手消息提交一次测试反馈，在 Dashboard 的智能体反馈中打开详情，再打开本轮 Langfuse Trace。

超级管理员可以在自身会话的调试面板中选择 Turn，打开整轮 Langfuse Trace。集中反馈入口按反馈记录定位所属 Turn，允许管理员复盘其他用户的反馈；原会话、文件与操作权限仍由各自接口执行。两个跳转接口只接受超级管理员产品 JWT，拒绝所有 API Key。Langfuse 项目的访问权限由 Langfuse 执行。

配置 Langfuse 的 Run 在模型执行前固化 Trace 关联，失败、取消或中断且没有最终输出时仍可跳转。同一 Turn 的恢复段共用 Trace；跳转只读取本轮持久关联。缺少 Trace、Langfuse 未配置或 URL 来源校验失败时，页面提示不可用。

Yuxi 在 PostgreSQL 保存本地 Model/Tool 审计事实，调试面板按 Turn 展示记录与持久状态，详情保留各 Run 阶段耗时。轮次总耗时包含等待与恢复间隔，时间概览继续累计各 Run 的执行窗口。本地审计独立于 Langfuse 导出，业务结果以 PostgreSQL 记录为准。

## 常见问题

- **看不到 trace**：检查 API/worker 是否都读取到公钥与密钥、Langfuse SDK 是否安装，以及 `LANGFUSE_BASE_URL` 是否可访问。
- **反馈无法打开 Trace**：确认反馈所属 Turn 已持久化 Trace 关联，并检查当前账号具有对应 Langfuse 项目的访问权限。
- **控制台显示旧数据**：Langfuse 客户端有缓冲，运行结束后会刷新；业务结果仍以 Yuxi 的 PostgreSQL 记录为准。

## 代码和测试入口

- [Langfuse 服务](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/services/tracing.py)
- [反馈服务](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/services/feedback.py)
- [Langfuse 单元测试](https://github.com/xerrors/Yuxi/blob/main/backend/test/unit/services/test_langfuse_service.py)
