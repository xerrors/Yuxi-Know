# 评估智能体

智能体评估用 Langfuse Dataset 保存一组固定任务，再让 Yuxi 按真实的 AgentRun、worker 和工具链路逐条执行。它适合比较一个智能体在研究、编程、文件处理或多步骤任务上的表现。

本页不介绍知识库的 `recall@K` 和答案指标；那部分见[知识库评估](../intro/evaluation.md)。

## 需要准备什么

1. Yuxi 已配置 Langfuse tracing，API/worker 环境包含：

   ```bash
   LANGFUSE_PUBLIC_KEY=<your-public-key>
   LANGFUSE_SECRET_KEY=<your-secret-key>
   LANGFUSE_BASE_URL=https://cloud.langfuse.com
   ```

2. 本机运行 CLI 时也能读取同一 Langfuse 项目的变量。CLI 会直接读取 Dataset 并创建 experiment。
3. 已安装 `yuxi-cli`，并登录目标实例：

   ```bash
   yuxi remote add local http://localhost:5173
   yuxi login --browser
   ```

   CI 或没有浏览器时，可以使用 `yuxi login --api-key "$YUXI_API_KEY"`。
4. 目标智能体已经存在，登录用户有权访问它。命令使用 Agent slug，例如 `default-chatbot`。

## 准备 Dataset

在 Langfuse 中创建 Dataset，并为每个 item 的 `input` 提供任务文本：

```json
{"input":"请整理这份资料，并列出三个需要核实的事实。"}
```

也兼容把任务放在 `query`、`question` 或 `prompt` 字段中。`expected_output` 可以保存参考答案，具体评分规则由 Langfuse evaluator 或人工评审负责。

Yuxi 不负责创建或上传 Dataset。先在 Langfuse 中检查任务文本、参考输出和数据集版本，再运行实验。

## 运行实验

```bash
yuxi agent eval \
  --dataset-name demo-dataset \
  --agent-slug default-chatbot \
  --experiment-name default-chatbot-demo \
  --max-concurrency 1 \
  --timeout-seconds 900
```

CLI 对每条 item：

1. 从 Dataset 读取任务文本；
2. 调用 Yuxi 的 `POST /api/agent-invocation/eval/runs`；
3. 由 Yuxi 创建临时 Conversation 和 AgentRun；
4. 通过 worker 执行真实智能体；
5. 等待 Run 进入终态；
6. 把最终输出写回 Langfuse experiment item。

`--max-concurrency` 是 Dataset 实验的并发数。先从 `1` 开始，再根据模型服务、worker 和沙盒容量提高。`--timeout-seconds` 是每条样例等待 Yuxi 结果的上限；超时会报告当前运行状态，不应把它当作成功。

## 查看结果

实验完成后，在 Langfuse Dataset 的 experiment 中查看每条 item 的最终输出。Yuxi 会在本地运行上下文和 trace 中保存以下标记，便于筛选：

```text
source=agent_evaluation
evaluation_dataset_name=<dataset-name>
evaluation_dataset_item_id=<item-id>
evaluation_experiment_name=<experiment-name>
```

先比较同一数据集的输出，再按自己的评估规则打分。一次实验的输出只代表当时的模型、Agent 配置、工具、知识库和外部服务状态；改变这些条件后，应创建新的 experiment 名称。

## 排查失败

- 没有 experiment：检查 CLI 的 Langfuse 公钥、密钥、地址和 Dataset 名称。
- experiment 有 item 但 Yuxi 失败：检查 CLI 登录的 API Key、Agent slug，并用 `docker compose logs api worker` 查看当前槽位日志。
- Trace 缺失：检查 API/worker 是否读取到 Langfuse 配置；Yuxi 业务结果仍以 PostgreSQL 的 Run 和消息为准。
- 大量超时：降低 `--max-concurrency`，检查模型响应时间、worker 健康状态和沙盒创建耗时。
- 实验部分成功：不要只看命令退出前的汇总，回到 Langfuse 检查每条 item 是否都有结果；CLI 会在成功写入数量与 Dataset 总数不一致时报告错误。

实现入口见 Agent Eval 路由 (`backend/server/routers/agent_invocation_eval_router.py`)、CLI 实验 (`packages/yuxi-cli/src/yuxi_cli/agent_eval.py`) 和 [Langfuse 集成](../advanced/langfuse-integration.md)。
