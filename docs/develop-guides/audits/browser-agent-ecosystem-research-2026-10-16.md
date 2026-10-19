# Agent 浏览器方案与 Yuxi 部署建议

面向 Yuxi 维护者，比较常见的开源浏览器自动化与 Agent 接入方案，回答运行依赖、登录态跨会话保存方式，以及浏览器软件应安装在什么镜像中。调研范围包括 Playwright、browser-use、Stagehand、Browserbase、Playwright MCP、Chrome DevTools MCP 和 Vercel agent-browser；不把 GitHub 星标解释为真实部署量或任务成功率。

调研日期为 2026-10-16。外部事实取自项目官方文档、官方 GitHub 仓库和 Chrome 官方文档；本地现状来自当前 Yuxi 文档、Cube 模板与部署文件。未安装候选项目。当前工作树保留原代码并已将真实业务库从 v1 事务迁移到 v4；API/Worker ready 后完成了真实网页路由、跨对话 profile 和图片 DOM 验证，结果见下文。

## 建议先复用现有 Playwright 与 Cube VM

Yuxi 已在 Cube 用户 VM 模板中安装固定版本的 Python Playwright、与其匹配的 Chromium 以及 Linux 系统库；当前模板把浏览器放在 `/home/user/.cache/ms-playwright`。每位用户拥有持久 VM，所有 Agent 对话复用该 VM 的普通账号和 Home。因此跨对话共用登录态不需要先增加 Browser Use、Stagehand 或 Browserbase，首要条件是每次操作使用同一个持久 `user_data_dir`，而不是关闭进程后丢弃的临时 BrowserContext。[沙盒运行机制](../../mechanisms/sandbox.md)、[沙盒运维说明](../../advanced/sandbox-operations.md)、[Cube 用户模板](https://github.com/xerrors/Yuxi/blob/main/docker/cube/Dockerfile.user)

Playwright 同时适合 E2E 测试和通用浏览器自动化；官方 Python 文档明确列出两种用途。把它称为“只能测试”不符合当前 API 能力。Yuxi 可以继续让 Agent 通过现有 `execute` 在用户 VM 中运行 Playwright，提示词明确适用任务和调用路径；框架替换不会自动教模型何时调用浏览器。[Playwright Python 安装文档](https://playwright.dev/python/docs/intro)

当前最小建议是：保留 Playwright；在 VM 内为用户设置固定、受限权限的浏览器数据目录；针对同一目录串行启动/关闭，避免同一用户的并行对话同时占用 Profile；用 A 对话登录、B 对话读取受保护页面的真实 DOM 作为验收。Yuxi 的显式“重建环境”会清除 VM，因此仅保存在 VM Home 的 Profile 会随重建丢失；若产品需要重建后仍保留登录态，再评估独立的用户级持久存储与权限边界。[沙盒运维说明](../../advanced/sandbox-operations.md)

## 开源方案处于不同层次

GitHub 项目页面在调研时显示 Playwright 约 97.8k 星、browser-use 约 118k、Chrome DevTools MCP 约 53.6k、Vercel agent-browser 约 44k、Playwright MCP 约 38.2k、Stagehand 约 25.7k。这些数字只说明项目受关注程度，不等于安装量、生产使用量或成功率；本文按用途比较，不据此给出严格排名。[Playwright](https://github.com/microsoft/playwright)、[browser-use](https://github.com/browser-use/browser-use)、[Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)、[agent-browser](https://github.com/vercel-labs/agent-browser)、[Playwright MCP](https://github.com/microsoft/playwright-mcp)、[Stagehand](https://github.com/browserbase/stagehand)

| 方案 | 所在层与适用点 | 框架代码依赖 | 浏览器与系统依赖、状态配置 |
| --- | --- | --- | --- |
| [Playwright](https://playwright.dev/python/docs/intro) | 浏览器自动化基础库；可写确定性脚本，也可作为 E2E 测试工具，支持 Chromium、Firefox、WebKit。 | Yuxi 当前使用 Python SDK；Python 项目安装 `playwright`。 | 浏览器二进制需通过 Playwright CLI 安装，Linux 还需浏览器系统库；包版本升级后要安装对应浏览器。用 `launch_persistent_context(user_data_dir=...)` 保存完整用户 Profile；同一数据目录不能同时打开多个浏览器。 |
| [browser-use](https://github.com/browser-use/browser-use) | Python Agent 浏览器框架，自带 Agent 循环、浏览器工具和系统提示；支持本地与托管浏览器。 | Python 3.11+，安装 `browser-use`；官方 Quickstart 用 `uvx browser-use install` 安装浏览器。当前项目依赖含 `cdp-use`，并把 `browser-use-core` 放在可选 `core` extra 中；不要假设它只是 Playwright 的薄封装。[项目依赖定义](https://github.com/browser-use/browser-use/blob/main/pyproject.toml) | `Browser` 支持 `user_data_dir`、`profile_directory` 与 `storage_state`；默认 Profile 是自动生成的临时目录，需显式指定稳定路径。云浏览器、Browser Use 模型网关及其 API Key 是可选付费服务，不是开源库的本地运行必要条件。[Quickstart](https://docs.browser-use.com/open-source/quickstart)、[Browser Settings](https://docs.browser-use.com/open-source/customize/browser/all-parameters) |
| [Stagehand](https://github.com/browserbase/stagehand) | Agent 自动化 SDK：`act`、`observe`、`extract` 等自然语言能力与确定性页面 API 混用；适合 UI 不稳定、需要结构化提取的流程。 | 官方提供 TypeScript、Python、Go SDK；本地 TypeScript 示例安装 `@browserbasehq/stagehand` 和兼容的 Zod，Python 安装 `stagehand`。 | 本地模式需要 Chrome；本地 `userDataDir` 会在进程关闭后保留。Browserbase 模式通过持久 context ID 保存云端状态并需要 API Key。Stagehand SDK 开源，Browserbase 云服务是单独托管服务。[Quickstart](https://docs.stagehand.dev/v4/first-steps/quickstart)、[User data](https://docs.stagehand.dev/v4/best-practices/user-data) |
| [Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp) | 将浏览器操作直接暴露为 MCP 工具，以可访问性树和结构化交互给模型使用；适合现有 Agent 能接 MCP、希望减少 shell 中手写脚本的场景。 | 官方 Quickstart 要求 Node.js 20+，通常以 `npx @playwright/mcp@latest` 启动；MCP 客户端还需注册工具配置。 | 运行本地 Playwright browser 所需 Chromium/Firefox/WebKit 二进制与 Linux 系统库仍需准备。官方配置文档提供 persistent profile、`--user-data-dir` 和 `--isolated` 模式；隔离模式会在关闭时丢弃存储。[Quickstart 与配置](https://github.com/microsoft/playwright/blob/main/docs/src/getting-started-mcp.md) |
| [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) | Chrome 专用 MCP 服务，除页面自动化外强调 DevTools、网络、控制台和性能追踪；适合调试或需要观察真实 Chrome 的工作流。 | Node.js LTS、npm/npx；官方启动配置为 `npx -y chrome-devtools-mcp@latest`，实现使用 Puppeteer 控制 Chrome。 | 需要当前稳定版 Chrome 或 Chrome for Testing；默认 Profile 位于用户缓存目录并跨运行保留，`--isolated` 临时隔离。也能连接既有 Chrome，但远程调试端口可让本机程序控制页面，必须限制连接面并使用专用 `--user-data-dir`。[要求与安装](https://github.com/ChromeDevTools/chrome-devtools-mcp#requirements)、[Profile 与连接配置](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/advanced-usage.md) |
| [Vercel agent-browser](https://github.com/vercel-labs/agent-browser) | 面向 Agent 的 CLI 和后台浏览器会话；Accessibility snapshot 与引用式点击可直接通过 shell 调用，适合希望比手写 Playwright 脚本更容易发现和执行工具的场景。 | CLI 通过 `npm install -g agent-browser` 安装预编译 Rust 二进制；Node.js/npm 用于安装，运行常驻 daemon 不要求 Node。源码构建才需要 Node、pnpm 和 Rust。 | `agent-browser install` 下载 Chrome for Testing；Linux 可用 `agent-browser install --with-deps` 安装系统库。支持稳定 `--profile` 与 `--session --restore`；恢复文件含认证状态，可用 AES-GCM 加密。CLI/daemon 要纳入 VM 模板和版本管理。[安装、状态与 Profile](https://github.com/vercel-labs/agent-browser#installation) |

Browserbase 本身是托管浏览器平台，依赖其云端 API、账户和凭据；它不是开源替代浏览器引擎。Stagehand 等 SDK 可以把本地 Chrome 与 Browserbase 作为可切换运行环境，Browserbase 可通过持久 context 保存云端登录态。它适合本地浏览器并发、维护或网络环境成为瓶颈后再评估，当前 Yuxi 已有持久用户 VM，尚无证据需要引入托管浏览器。[Stagehand User data](https://docs.stagehand.dev/v4/best-practices/user-data)、[Browserbase + Stagehand 示例](https://docs.browserbase.com/integrations/vercel/quickstart)

## 对话 A 登录后，对话 B 怎样复用

“保存登录信息”有两种实现，覆盖范围不同：

| 方法 | 能保存什么 | 适用边界 |
| --- | --- | --- |
| 固定持久 Profile | 浏览器的用户数据目录；Cookies、Local Storage、IndexedDB、缓存和站点 Profile 状态留在浏览器自己管理的目录。 | 适合用户希望后续对话继续使用同一浏览器状态。Playwright 用 `launch_persistent_context(user_data_dir)`；该目录应固定在该用户的持久 VM 文件系统内。浏览器必须独占该目录，Yuxi 要将同一 Profile 的操作串行化，或由一个受控浏览器进程统一拥有它。[Playwright BrowserType API](https://playwright.dev/python/docs/api/class-browsertype) |
| `storage_state` 文件 | Playwright 可导出 Cookies 与 Local Storage；IndexedDB 需显式开启，最新 API 另有 OPFS 和虚拟 WebAuthn 选项。它是存储快照，不是整个浏览器缓存/历史/Profile。`sessionStorage` 不在默认存储快照中。 | 适合将登录状态复制给独立的临时 BrowserContext；不满足“完整缓存”语义。状态文件可以代表用户账号，Playwright 明确警告不要提交到代码仓库。[Playwright Auth](https://playwright.dev/python/docs/auth)、[BrowserContext `storage_state`](https://playwright.dev/python/docs/api/class-browsercontext) |

跨对话实测在 example.com 对话 A 写入并读回合成 `localStorage` 标记，关闭浏览器后重启 API/Worker；独立对话 B 读到相同值。数据库回读确认两次运行成功，用户 VM generation 保持 2。此结果证明同一 VM 上 profile 跨对话及 API/Worker 重启复用，不证明真实第三方登录、VM 暂停/恢复或 VM 重建后的行为；测试未使用真实账号。

同一 Profile 只能由一个浏览器实例同时使用。Yuxi 每用户 VM 可运行并发 Agent，因此“固定路径”单独不足以避免锁冲突和标签页互相干扰。最小做法是在执行边界按用户 Profile 加锁，同一时间只允许一个 Run 启动该 Profile；需要并发时再设计每用户单一浏览器 Owner 和会话隔离。不要把 Profile 挂载为所有用户共享目录。[Playwright `launch_persistent_context`](https://playwright.dev/python/docs/api/class-browsertype)、[Chrome DevTools MCP 并发与 Profile 说明](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/advanced-usage.md)

Chrome 136 起，Chrome 不再对默认数据目录响应 `--remote-debugging-port` 或 `--remote-debugging-pipe`；远程调试必须配合非默认 `--user-data-dir`。Chrome 官方将此改动归因于避免利用远程调试窃取 Cookie，并建议把调试 Profile 与真实个人 Profile 隔离。因此不要把用户桌面 Chrome 默认 Profile 直接开放给 Agent，也不要把 CDP 端口暴露到 VM 外网。[Chrome 官方远程调试安全说明](https://developer.chrome.com/blog/remote-debugging-port?hl=zh-CN)

## 区分代码包、浏览器二进制和系统库

浏览器方案通常由三层依赖组成，配置好 Python/Node 包并不等于可启动浏览器：

| 层 | 示例 | 放置位置与更新方式 |
| --- | --- | --- |
| Agent/自动化代码包 | Python `playwright` / `browser-use` / `stagehand`；Node `@playwright/mcp`、`chrome-devtools-mcp`、`agent-browser` | 放在实际运行 Agent 工具的环境。Yuxi 的 Agent 命令在 Cube 用户 VM 执行，因此无需把 Playwright 或 Node 浏览器 MCP 包安装到 API/Worker 服务容器。 |
| 浏览器可执行程序 | Playwright 匹配的 Chromium，或 Chrome for Testing/Stable | 在用户 VM 模板构建阶段安装，避免对话首次运行时下载。Playwright 要求安装与其版本匹配的 browser binary；CLI 可用 `playwright install chromium` 下载指定浏览器。[Playwright 浏览器安装](https://playwright.dev/python/docs/browsers) |
| Linux 系统依赖 | Chromium 启动所需共享库、字体和 sandbox 运行条件 | 在 VM 镜像构建阶段安装，例如 Playwright 的 `playwright install --with-deps chromium` 会组合浏览器下载与浏览器 OS 依赖安装。更新时把 Python 包、浏览器版本和系统依赖作为同一镜像版本验证。[Playwright 浏览器与 OS 依赖](https://playwright.dev/python/docs/browsers#install-system-dependencies) |

当前 Yuxi 模板已经按第三层方式构建：`docker/cube/Dockerfile.user` 固定 Playwright 1.64.0，并在镜像构建时运行 Chromium 安装与系统依赖安装；[运维文档](../../advanced/sandbox-operations.md)说明模板更新影响新建 VM，已有 VM 需要显式重建。因此升级模板不会因为重启 API 和 Worker 就自动改写已经存在的用户 VM；发布前要明确现有用户实例的更新策略与数据影响。

对于本地 Python Playwright 方案，不需要 Node.js。采用 MCP 或 CLI 时才增加 Node/npm 层；Chrome DevTools MCP 还需要 Chrome。browser-use Python 库可使用自己的本地浏览器安装命令；Stagehand 本地运行需 Chrome；Browserbase 云端运行可免本地浏览器，但增加供应商 API 凭据、网络依赖和云端数据边界。根据真实运行位置选择安装项，不在 API、worker、Cube 主机和 VM 模板中重复安装一套未使用的浏览器。

## 对 Yuxi 的务实取舍

1. 保持现有 Python Playwright/Chromium VM 模板。它已满足读取网页、交互、截图和下载的运行条件。按受支持的 Playwright 升级流程同步更新包与 Chromium，再通过模板版本供新 VM 使用；不要只把 Python 包更新到“latest”而留下旧浏览器二进制。
2. 先实现跨对话 Profile 复用与串行所有权，不先增加 Agent 框架。Profile 本身提供登录和缓存持久化，提示词负责在需要当前网页事实、访问网站、交互或截图时调用 `execute`；静态知识整理、纯文本改写和用户明确要求不联网时不应强行调用浏览器。
3. 如果 Playwright 代码通过 shell 使用对模型太隐蔽，可先对比 Vercel agent-browser CLI 与现有流程。它的 snapshot、引用式操作、稳定 session 和 profile 恢复接口适合 Agent 工具调用，但引入了新的 CLI、daemon、Chrome for Testing 和密钥状态存储面；需用 Yuxi 的真实对话 E2E 证明可发现性和最终 DOM 行为有收益。[agent-browser README](https://github.com/vercel-labs/agent-browser)
4. 如果 Yuxi 决定将浏览器操作作为一等 MCP 工具，Playwright MCP 与 Chrome DevTools MCP 是现成候选：前者通用、基于 Playwright 可访问性树；后者面向 Chrome DevTools、网络和性能诊断。都需要 MCP server 启动、工具注册、用户 VM Node 运行环境和并发/Profile 生命周期管理，现有 Cube 安装 Playwright 并不会自动提供这些能力。[Playwright MCP](https://github.com/microsoft/playwright-mcp)、[Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)
5. 只有在需要自然语言弹性操作、跨域结构化抽取时评估 Stagehand；只有在需要它自带的 Agent 循环或云浏览器时评估 browser-use。两者都带来新的模型层、配置、依赖和故障边界，不会替代 Yuxi 对工具可见性、授权或操作验证的责任。Browserbase 是后续可选托管基础设施，而不是开源部署依赖。

本调研结论状态为 `Inspected`：读取了本地沙盒文档、模板构建文件和各方案官方文档/仓库；GitHub 星标只作为项目关注度快照。真实 Yuxi 对话验证显示，稳定常识没有触发工具。旧提示词下，一项简单官方文档事实触发 4 次 `web_search` 和 4 次结果 `grep`；提示词改为简单问题最多搜索一次后，新对话只调用 1 次 `web_search`、读取一次结果并引用官方链接。指定页面任务按需读取 browser 与 chat-widgets Skill，调用 Playwright 打开 example.com 并保存截图；数据库中的最终回复使用 Image Widget，真实 DOM 图片尺寸为 1280×823，且没有 `present_artifacts` 调用。A/B 标记结果见上文。

数据库 schema v1→v4 已在部署侧直接调整，应用代码没有保留历史迁移脚本；数据处置与备份校验见[数据库调整记录](../decisions/implemented/2026-10-19-schema-baseline-one.md)。浏览器操作接入官方 `agent-browser` 和 `playwright-cli` Skill，推荐入口、按需安装与 CLI 配置边界见[浏览器能力决策](../decisions/implemented/2026-10-16-agent-browser-capability-boundary.md)。上文 Python Playwright 基线结果不覆盖两个 CLI 的运行与登录态。

仍未验证真实第三方账号登录、同一用户并行 Profile 冲突、VM 重建后的状态保留、浏览器镜像体积和运行性能。开源候选项目均为文档调研，没有安装对比。
