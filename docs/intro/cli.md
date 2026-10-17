# 使用命令行工具

`@xerrors/yuxi` 是 Yuxi 的 npm 命令行客户端，要求 Node.js 22 或更高版本。它通过 Public v1 查看智能体、对话、发送附件与图片、查询知识库，并保存多个远程实例。开始前需要一套已启动、配置好模型和智能体的 Yuxi。完成本页后，可以在终端对话并核对持久结果。

## 安装

从仓库根目录构建并安装本地包：

```bash
cd packages/yuxi-cli
npm ci
npm test
npm pack
npm install --global ./xerrors-yuxi-0.1.0.tgz
yuxi --version
```

`yuxi --version` 输出包版本。调试源码时，使用 `npm run build` 后的 `node dist/cli.js` 代替 `yuxi`；修改 TypeScript 后需要重新构建。

维护者发布到 npm 后，也可以使用 `npm install --global @xerrors/yuxi` 安装，或使用 `npx @xerrors/yuxi --help` 临时运行。包的构建与发布规则见[贡献指南](../develop-guides/contributing.md#候选版本与正式发布)。

## 连接实例

保存实例入口地址，再选择当前实例：

```bash
yuxi remote add production https://example.com
yuxi remote use production
yuxi remote list
yuxi remote ping
```

`remote list` 中的 `*` 表示当前实例；`remote ping` 返回服务健康状态和版本。健康检查只证明 API 进程可达，对话还需要服务端 worker 和模型配置就绪。

配置保存在 `~/.yuxi/config.json`，API Key 以明文保存，POSIX 文件权限为 `0600`。实例地址会去掉末尾 `/api` 并在请求时派生 API 路径；不要填写具体接口地址。修改已有 remote 的 URL 会清除该 remote 的登录凭据。

命令默认使用 `remote use` 选择的实例。`--remote <name>`（简写 `-r`）只覆盖本次命令的选择；`remote ping <name>` 用位置参数指定实例。CLI 配置格式由当前 npm 包维护，连接新实例后先登录再调用需要身份的接口。

## 登录和退出

浏览器登录使用当前 remote，终端会打印授权码和授权地址：

```bash
yuxi login
```

浏览器中登录 Yuxi 并确认授权后，CLI 保存 API Key。无法自动打开浏览器时，使用 `yuxi login --no-open`，手动打开终端输出的地址。

也可以导入已有 API Key：

```bash
yuxi login --api-key "$YUXI_API_KEY"
yuxi whoami
yuxi status
```

使用环境变量可以避免把密钥值直接写进 Shell 历史，参数仍会出现在本机进程参数中。生产环境使用 HTTPS，保护本地配置文件，不将密钥、配置或授权码放进仓库与公开日志。API Key 的服务端权限见[API Key 接入](../advanced/api-key-integration.md)。

退出当前 remote：

```bash
yuxi logout
```

通过浏览器登录创建的 Key 会在退出时撤销；导入的 Key 没有保存服务端 ID，只清除本地凭据。需要保留浏览器创建的 Key 时使用 `yuxi logout --local-only`。

## 在终端对话

先确认可用智能体，再启动 Chat：

```bash
yuxi agent list
yuxi agent show default-chatbot
yuxi chat --agent default-chatbot
```

Agent 目录和详情展示 Public v1 的公开字段：ID、名称、描述；模型、系统提示词和工具配置属于管理界面。`chat` 默认使用 `default-chatbot`，启动时打印新 Thread ID。在 `> ` 后输入文本，回复逐段显示并保留换行；回复结束后出现新的提示符。

```text
> 请分两行回复，第一行写甲，第二行写乙。
甲
乙
> /exit
```

`/exit` 或 `/quit` 退出终端交互，Thread 历史保留在服务端。对话会尝试通过 SSE cursor 和持久 Turn 结果恢复断流；运行失败、取消或恢复失败时，CLI 返回非零退出码。审批和回答等待点需要在 Yuxi 网页继续。交互式 `chat` 接收文本，附件和图片通过下面的 `thread send` 提交。

## 查看 Thread

CLI 的 `thread` 命令操作 Public API 的 Session，使用 Chat 打印的 Thread ID 读取状态、历史或提交后续消息：

```bash
yuxi thread list --agent default-chatbot
yuxi thread show <thread-id>
yuxi thread history <thread-id>
yuxi thread send <thread-id> "继续解释第二点"
yuxi thread watch <thread-id>
```

`thread send` 输出持久 Input 回执，接收成功不代表运行完成。`thread watch` 持续输出逐条事件 JSON，在标准错误流中显示恢复 cursor；使用 `--cursor <cursor>` 从该位置订阅，按 `Ctrl+C` 停止观察。Thread、Turn 和 Input 的语义见[智能体 Public API](../advanced/agents-public-api.md)。

`send` 在提交前打印幂等键。响应丢失时，先按该键查询回执；仍未找到接收记录时，使用原消息和原键重试。通过 Input 的 `turn_id` 找到本次工作，再读取对应 Turn 的 `yuxi.output`：

```bash
yuxi thread receipt <thread-id> <saved-key>
yuxi thread send <thread-id> "继续解释第二点" --idempotency-key <saved-key>
yuxi thread input <thread-id> <input-id>
yuxi thread turn <thread-id> <turn-id>
```

列表和历史使用游标分页；`has_more=true` 时，将返回的 `last_id` 传给下一页的 `--after`。Turn 列表也包含尚未生成消息的工作：

```bash
yuxi thread history <thread-id> --limit 20 --order asc --after <last-id>
yuxi thread turns <thread-id> --limit 20
```

查询命令可以加 `--json`，供脚本读取原始响应：

```bash
yuxi agent list --json
yuxi thread show <thread-id> --json
```

## 发送附件和图片

先上传文件草稿，读取返回的 `id`，再随消息提交：

```bash
yuxi file upload ./report.pdf --mime-type application/pdf
yuxi file show <draft-id>
yuxi thread send <thread-id> "总结这份报告" --file-id <draft-id>
```

上传草稿不会创建 Session 或写入 Workdir。接收消息后文件才绑定到 Input，准备就绪后随输入消费进入对话。尚未提交的草稿可以用 `yuxi file delete <draft-id>` 删除；已提交文件的归属、有效期与重试规则见[附件协议](../advanced/agents-public-api.md#图片与文件附件)。

`thread send --image-url` 接收完整的 `data:image/...;base64,...` URL，需保留实际 MIME；例如下面的 `IMAGE_DATA_URL` 由调用方提供：

```bash
yuxi thread send <thread-id> "描述这张图片" --image-url "$IMAGE_DATA_URL"
```

图片会作为视觉输入发送，能否识别取决于所选模型；文件附件由智能体按需读取或解析。CLI 不调用产品私有的图片预处理或手动 OCR 接口。

## 查询知识库

登录用户通过 Public 工具接口读取自己有权限访问的知识库：

```bash
yuxi kb list
yuxi kb files --kb-id <kb-id>
yuxi kb files --kb-id <kb-id> --query handbook
yuxi kb query --kb-id <kb-id> "如何申请年假？"
```

先用 `files` 找到文件 ID，再打开解析内容或搜索匹配窗口：

```bash
yuxi kb open --kb-id <kb-id> --file-id <file-id>
yuxi kb find --kb-id <kb-id> --file-id <file-id> --pattern "年假"
```

`kb files --query` 只匹配文件名；`kb query` 返回检索结果；`kb open` 返回内容窗口；`kb find` 使用 Public v1 文件查找接口。命令只读，不创建、上传、解析或索引文件。需要脚本处理原始响应时，给这些命令加 `--json`。

## 能力边界 {#第一阶段的边界}

当前 npm CLI 不包含以下能力：

- Agent eval、Langfuse Dataset experiment；
- 知识库上传、解析、索引和管理；
- MCP、Skill、模型和系统配置管理；
- 工具审批和等待点恢复。

管理能力和等待交互使用 Web 界面或对应后端接口。完整智能体评估由调用方通过公开 API 构建，见[智能体评估](../agents/agent-evaluation.md)。

## 排查

如果命令找不到，确认全局安装的包和当前构建目录不是两个版本：

```bash
which yuxi
yuxi --version
cd packages/yuxi-cli
npm run typecheck
npm test
npm run build
```

如果 `login` 报服务版本或 discovery 错误，先运行 `yuxi remote ping`，再确认实例提供 Public v1 和 CLI auth 能力。`chat` 返回非零退出时，保留 Thread ID，并用 `thread show`、`thread history` 和服务端日志检查持久状态；不要只依据终端最后一行判断 Turn 结果。
