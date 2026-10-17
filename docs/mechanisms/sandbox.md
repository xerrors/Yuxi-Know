# 沙盒与文件系统机制

每个用户固定一个持久 Cube VM。所有 Agent 对话共用普通账号 `user` 的软件、Home 和配置，自然并发执行；项目的 cwd、Run 结果、协作身份和执行名额仍分别管理。Agent 没有 sudo 权限，平台控制凭据不进入 VM 的环境变量或模型上下文。

## 文件边界

| 路径 | 文件 Owner | 是否唤醒 VM |
|---|---|---|
| `/home/user/workspace`、`~/workspace` | 宿主 UserWorkspace，读写同一份文件 | 否 |
| Workspace 内的 `agents/skills` | 用户个人 Skills，可写 | 否 |
| `/home/user/skills` | 用户获授权的共享投影，只读 | 否 |
| `/home/user/.config`、venv、其他普通账号可访问路径 | VM 文件系统 | 是 |

`/home/user/workspace` 是当前用户 UserWorkspace 的直接可写持久挂载，`~/workspace` 是同一绝对路径的 Home 缩写。`/home/user/skills` 是获授权共享 Skills 的只读投影。固定路径由 `modules/workspace/runtime_paths.py` 拥有，Cube provider、文件工具、附件、产物与 Viewer 共用此契约。路径没有环境变量覆盖或历史别名。

默认 Project 工作目录位于 Workspace 的 `projects/YYYYMMDD/<六位标识>`，日期使用上海时间，标识取 Project UUID 前六位。路径分配避开用户已有文件和数据库目录绑定，重名按顺序添加 `-1`、`-2` 后缀。目录在数据库绑定提交后物化；已有时间戳目录继续按原绑定访问。手动创建的 linked Project 使用用户选择的现有目录。生成与校验由 `modules/workspace/paths.py` 拥有，取舍见[目录分层决策](../develop-guides/decisions/implemented/2026-10-15-project-workdir-date-layout.md)。

`runtime/sandbox/backend.py` 保持现有文件和 execute 工具返回协议。`modules/workspace/runtime_files.py` 将共享路径交给宿主文件边界，拒绝 symlink 越界；其他路径通过固定普通账号的受追踪进程访问。Cube v0.7.3 的 HTTP 文件接口不能证明普通用户权限，因此不使用该接口；读写、编辑和搜索均由 VM 内核执行权限边界。模型不能指定执行账号。

共享 Workspace 是用户工作文件，不是 Home 的备份。成果登记、预览和下载继续读取 Workspace 的最新文件；Home 中的成果需要先复制到 Workspace。个人 Skills 位于 Workspace 的 `agents/skills`，共享投影只包含用户获授权的来源。远程 Skill CLI 在操作者 VM 的请求专属目录中运行，宿主安装边界校验发布文件，只清理该请求目录。

## 生命周期与并发

超级管理员的系统概览显示执行节点当前活跃 VM 数量与 VM 总数。`GET /api/dashboard/stats/vms` 只读配置节点的全部实例列表，运行中的实例计为活跃，休眠等其他实例计入总数；不会连接或唤醒 VM。数量在进入概览或点击 VM 总数旁的刷新按钮时更新，控制面不可用时显示未知值并提供重试，其他业务统计继续展示。

PostgreSQL 的 `user_sandboxes` 保存实例引用、代次、控制凭据和操作状态，`sandbox_commands` 保存所属 Run/attempt、执行标识与进程组。用户 advisory lock 协调创建、唤醒、休眠、重建与执行领取；命令运行期间不持有用户锁，因此同用户命令可以并行。

首次远端操作创建 VM，休眠后恢复原实例。默认空闲五分钟且没有活动 Run、文件操作或待清理命令时，worker 暂停 VM。状态查询和宿主文件编辑不延长 VM 活动时间。API/worker 关闭不删除环境。控制面断流或实例失联显式报错，不自动重建或盲目重试创建；中断创建通过操作标识核对 Cube 实际实例。

Run 取消监听直接清理所属命令，超时与 lease 失效清理由持久句柄恢复。执行标识、环境代次和进程组一起核验，不能取消另一个 Run 或新代次 VM。清理直接启动普通用户 Python，不读取用户 shell 启动配置。终止未确认时保留待清理状态，阻止休眠与重建，无关命令可以继续。主动 `setsid` 脱离的守护进程不在普通进程组取消保证内。

用户设置提供 `GET /api/user/sandbox` 和 `POST /api/user/sandbox/rebuild`。认证上下文决定用户身份，没有删除接口或 Public API。正在运行、取消收尾的 Run 和活动操作阻止重建，后端在用户锁内再次检查并返回 409。空闲确认后替换 VM 并增加代次，清除软件和 Home，保留 Workspace 与 Skills。

单节点部署要求见[沙盒配置与运维](../advanced/sandbox-operations.md)。当前验证使用嵌套 KVM 节点，原生节点重启恢复和资源压力隔离尚未验证。后台进程在休眠恢复后的连续运行不是产品承诺。

用户环境变量由 `services/environment.py` 保存和验证，runner 在开始执行流时使用已有数据库 session 读取一次快照，普通 shell 命令通过执行上下文复用。快照不进入运行清单或 checkpoint，退出后释放，重试 attempt 重新读取。无 Run 操作及手动验证读取最新配置，文件及清理进程使用独立干净环境。`POST /api/user/agent-env/verify` 通过同一持久命令执行器访问当前用户 VM，不改变当前 Run 或已有进程的环境变量；生效时机、结果边界与页面操作见[用户 Agent 环境变量](../advanced/configuration.md#用户-agent-环境变量)。
