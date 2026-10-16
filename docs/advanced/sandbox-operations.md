# 沙盒配置与运维

Yuxi 固定使用 CubeSandbox v0.7.3 的用户 VM。服务继续使用 Compose，执行节点必须是专用 Linux/KVM，Yuxi 与 Cube 的 Workspace/Skills 挂载必须指向同一份文件。旧 Docker/Kubernetes provider、provisioner 和 Docker socket 挂载已删除，没有运行时回退。

## 原生执行节点

在专用执行节点以管理员运行 `docker/cube/setup-node.sh` 安装 Cube，上传 `Dockerfile.user` 和 `build-template.sh` 到 `/opt/yuxi-cube` 后运行后者。安装脚本会将该节点的 SELinux 设为 permissive；脚本只用于专用执行节点，不能运行在 Yuxi 应用容器或用户 VM。普通账号 UID/GID 固定 1000，与 API/worker 文件身份一致，禁用 sudo。模板更新只影响新建实例；现有实例采用下文的显式重建流程，并先确认 Home 文件的保留需求。

默认开发工具链为 Node 24、npm/npx、Python 3.13.15、pip、venv、uv/uvx 0.12.6 和 Git。`python`、`python3`、`pip`、`pip3` 指向模板提供的 Python 3.13；Ubuntu 的 `/usr/bin/python3` 保留供系统和内部文件操作使用。项目优先通过 `uv venv` 和 `uv pip install --python .venv/bin/python <package>` 安装依赖，其他 Python 版本由 uv 在用户 Home 中按需管理。

模板预装 `curl wget jq ripgrep file zip unzip`、Noto CJK 和 Poppler PDF 工具。默认 Python 提供固定版本的 Playwright、httpx、BeautifulSoup、Pillow、openpyxl、PyMySQL；uv 新建的独立虚拟环境仍按项目声明依赖。Playwright 配套的 Chromium 和系统库在模板构建时安装，浏览器缓存位于 `/home/user/.cache/ms-playwright`，普通账号可直接通过 `python -m playwright` 或 `playwright` 使用。默认执行无头浏览器，不启动桌面、VNC 或常驻浏览器服务；包和浏览器需配套升级，实际能力由普通用户的截图、下载及 PDF 产物回读验证。

Skills 页的推荐区提供“浏览器与网页自动化”分组，可按需安装 Vercel [agent-browser](https://github.com/vercel-labs/agent-browser) 或 Microsoft [playwright-cli](https://github.com/microsoft/playwright-cli) 官方 Skill。Skill 提供操作指南，所需 CLI 和浏览器依赖按上游指南安装在用户 VM；预装的 Python Playwright 不提供这两个 CLI。

浏览器 profile、session 与登录状态的复用由所选 CLI 的实际配置管理，系统提示词只负责选择浏览器 Skill。agent-browser 跨浏览器重启保存状态需要显式配置持久 profile 或状态恢复，详见[上游会话文档](https://agent-browser.dev/sessions)。不同用户有各自的 VM Home；显式重建既有 VM 前需按下文确认 Home 数据保留，因为重建可能清除浏览器配置。

配置 Yuxi 的 `.env` / `.env.prod`：

```dotenv
CUBE_API_URL=http://<private-node-address>:3000
CUBE_API_KEY=<control-api-key-if-configured>
CUBE_PROXY_NODE_IP=<private-node-address>
CUBE_PROXY_PORT_HTTP=80
CUBE_TEMPLATE_ID=yuxi-user
CUBE_NODE_USER_DATA_DIR=/data/shared/yuxi/threads
CUBE_NODE_SKILL_PROJECTION_DIR=/data/shared/yuxi/skill-projections
SANDBOX_IDLE_SECONDS=300
```

两个 `CUBE_NODE_*` 值都是执行节点上的目录，分别与 API/worker 的 `/app/user-data`、`/app/skill-projections` 指向同一份底层文件；容器路径不能直接当成节点路径。示例要求管理员先将这两份存储共享或绑定到执行节点的 `/data/shared/yuxi` 下，符合 CubeMaster 默认的 `/data/shared/` 挂载白名单；设置环境变量不会创建共享挂载。使用其他节点目录时，管理员在 `extra_conf.allowed_host_mount_prefixes` 中显式配置所需窄前缀。

每个用户 VM 只挂载其 Workspace 子目录和授权 Skills 投影，投影只读；平台来源目录、数据库目录、`.env` 和 Docker socket 均不挂载。控制面及数据代理通过私网供 API/worker 访问，不作为公网产品接口开放。VM 默认禁止私网出口，外网包安装可用。

```bash
docker compose build api
docker compose run --rm schema-init
docker compose up -d api worker frontend
```

API/worker 启动检查控制面、模板及代理。`/api/system/ready` 仍是业务核心依赖门槛；某个用户实例的健康与占用由用户设置查看。用户环境变量在 Run 开始执行时从数据库读取一次，同次执行的命令共用快照，不继承平台进程环境；保存与验证语义见[用户 Agent 环境变量](./configuration.md#用户-agent-环境变量)。不要把管理密钥放入用户环境或 Skill。

## 当前机器的嵌套开发节点

`docker/cube/compose.yml` 与 `run-vm.sh` 仅帮助在当前机器开发验证。准备私有 `node.env`，内容包括 `CUBE_GUEST_BOOTSTRAP_PASSWORD`、`CUBE_DATA_DIR`、`CUBE_SHARED_DIR`、`CUBE_GATEWAY_IP`、`CUBE_KVM_GID`。共享目录应为 Yuxi state 下的 `yuxi`，其中包含 `threads` 和 `skill-projections`。文件与 Home 实例不是节点 qcow2 的迁移包。

```bash
docker compose --env-file .yuxi/cube-node/node.env -f docker/cube/compose.yml up -d --build
```

在开发节点 Guest 内以管理员运行 `setup-node.sh --nested`，外层 virtiofs 会挂到 `/data/shared/yuxi`；Yuxi 配置对应 `/data/shared/yuxi/threads`、`/data/shared/yuxi/skill-projections`。当前 Docker gateway 暴露控制端口 13001、代理端口 18081，宿主调试分别使用 13000、18080，SSH 为本机 10022。容器仅给可信文件导出节点必要的文件身份能力，没有授予用户 VM。外层 virtiofs 设备显式使用 `queue-size=1024`，缓存策略为 `cache=never`，关闭子挂载通告；实际启动配置由 [run-vm.sh](https://github.com/xerrors/Yuxi/blob/main/docker/cube/run-vm.sh) 拥有。

开发 Compose 的 API 与 worker 通过显式重启加载源码，前端保留 Vite 热更新；操作命令见[开发环境](../develop-guides/contributing.md#_2-开发环境)。

## 运维与验证

设置中查看环境状态、占用 Run 和待清理操作。状态和时间在一行展示；休眠时显示已休眠时长，悬停查看平台确认休眠的准确时间。旧记录或外部暂停没有可确认的时间时，显示“时间未记录”。运行空闲时显示预计休眠倒计时，使用实际配置的空闲阈值；有活动任务、操作或待清理命令时暂不休眠。倒计时到达只表示达到空闲时限，实际休眠由维护循环确认；页面每 15 秒重新查询状态，每秒更新时长，查询不会唤醒环境。

磁盘用量通过磁盘行的“查看”或“刷新”手动读取，显示上次查询的已用和可用空间。休眠时查询会恢复环境并重新开始空闲计时；自动状态刷新不执行磁盘查询。统计系统和主目录所在文件系统，不含共享工作区，也不表示宿主机镜像的物理分摊或独占配额。

重建入口位于状态行右侧的“···”菜单，只有“重建环境”一个选项，点击后确认清除范围。忙碌时先使用已有 Run 取消入口，等清理确认后重建。实例失联不要手工修改数据库为成功；核对 Cube 状态、实例标识与操作标识，恢复执行节点或确认重建。重建只清除 VM，宿主 Workspace 和 Skills 必须保留。不提供保留软件的冷重启接口，服务进程重启只重连原环境。

```bash
docker compose logs --tail=100 api worker
docker compose exec -T api uv run --group test pytest test/integration/sandbox/test_cube_user_environment.py -q
docker compose exec -T api uv run --group test pytest test/e2e/test_cube_agent_execution_e2e.py -q
# 可重放的并发 I/O 与命令 fuzz，JUnit properties 保存每组延迟与吞吐
docker compose exec -T api uv run --group test pytest test/integration/sandbox/test_cube_shared_mount_fuzz.py -q -o junit_family=legacy --junitxml=/tmp/cube-fuzz-results.xml
# 仅在无其他用户活动的独立测试拓扑中运行两 worker / 崩溃恢复验收
CUBE_TEST_ISOLATED_TOPOLOGY=1 bash scripts/test_cube_worker_recovery.sh
```

共享挂载持续阻塞时，核对执行节点的 `mount` 进程是否处于 D 状态，以及调用栈是否停在 FUSE 请求等待。节点进程存活和控制面健康只证明服务在线；恢复验收需执行文件和命令并回读产物。维护前停止接收新任务，核对活动 Run 和命令，保存用户环境引用、共享文件备份与字节校验，并在节点停止后备份其磁盘。恢复节点后，核对原实例标识和代次，验证 Home、Workspace、休眠和唤醒，保持已有用户 VM 的软件与配置。

fuzz 使用测试用户、固定 seed、1/2/4/8 并发、4 KiB 至 1 MiB 文件和含空格、引号、中文、换行的文件名；每组包含原子替换、宿主哈希回读和原实例休眠恢复。恢复后先核对休眠前文件的字节，再写入新内容；旧文件缺失时测试必须失败。随机命令覆盖正常及非零退出，核对输出归属与持久句柄清理。报告中的吞吐是该拓扑的批量写入吞吐，延迟包含控制连接和命令收尾；这些样本用于回归与比较，不定义生产容量阈值。

系统 CI 执行整个 `test/integration/sandbox` 子树，包含共享文件与命令 fuzz，使用带 `yuxi-cube` 标签的专用 Linux/KVM runner，预装 Cube 和用户模板，并通过 repository vars 配置控制面与代理，通过 secret 配置可选 API key。runner 与 Cube 必须访问同一 checkout 文件路径；单个节点不能同时运行两个争用固定 Compose 端口的 runner。缺少节点或变量时测试应失败，不跳过沙盒验收。未配置的远程 runner、原生节点重启恢复和资源压力测试不能据本机开发结果标记为上线通过。

## 路径与部署边界

VM 直接挂载 `/home/user/workspace` 和只读 `/home/user/skills`，模板在构建时创建这两个目录。API、worker、模板和测试使用同一组固定路径。宿主的 `/app/user-data` 与节点共享目录是存储位置，由 Workspace 管理，不能当成 VM 的路径传给模型。

文件工具、HTTP 预览、下载和保存对同一持久路径读取同一用户挂载：Workspace 读取用户工作区，Skills 读取用户投影。HTTP 请求先校验当前 Thread、APP、用户和 Skill 授权；投影缺失返回不存在，不读取平台来源代替。持久文件预览不唤醒 VM；Home 或临时目录中的图片先保存到当前 Project 工作目录再展示。

`grep` 在 Workspace 挂载与 VM 目录中默认最多返回 1000 条匹配，显式 `max_count` 必须为正数。只有发现超出上限的额外匹配才标记截断；恰好达到上限的完整结果保持未截断。

部署使用符合当前 Schema 基线的数据与新建用户环境。已有旧挂载 VM、旧附件引用和旧 checkpoint 不会被自动转换或重建；保留资料时先备份，由部署者离线处理路径和结构后核对文件字节及引用。应用不提供双路径读取或旧对象恢复。重建会清除 VM Home 中的软件和配置，保留 Workspace 和 Skills。
