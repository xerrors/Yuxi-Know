# GitHub 托管执行器与 Cube 测试边界

状态：implemented
类型：process
Owner：.github/workflows/system-tests.yml

## 问题

运行链路的两个 job 都依赖未注册的 self-hosted runner，数据库和局部 HTTP 测试也随完整 Cube 拓扑排队。GitHub Linux 执行器暴露 KVM 的文档不能直接证明 Cube 模板、网络和共享挂载兼容。

## 决策

### 实现方案

在 ubuntu-24.04 托管执行器上运行独立探针，依次验证 KVM 客体执行、固定版本 Cube 安装、正式用户模板和真实沙盒文件回读。安装只允许在 GitHub 的临时托管执行器上执行。探针不使用仓库凭据，不代替完整系统 E2E。

`service-integration.yml` 使用托管执行器与临时 PostgreSQL/Redis；`scripts/ci_run_service_integration.sh` 拥有迁移的 18 个测试文件选择器，Cube 任务删除相同选择器。脚本要求显式数据库、Redis、Skill 路径并拒绝本地 backend/.env，通过应用初始化和正式身份服务创建一次性基线管理员，再在 Cube/共享 API 不可达时执行测试。完整 API、shipping worker、对象存储和沙盒链路仍保留原有验证，不增加运行时降级。

Schema 崩溃恢复测试调用当前 `initialize_schema(manager)` 入口，继续通过真实进程退出、持久 initializing 标记与重试后的 Schema 证明恢复。迁移的 Schema、FIFO 和 lease 门禁由独立服务选择器的实际 pytest 命令及负控维护；工程 verifier 接线指向新工作流。

## 替代方案

- 全部保留在 self-hosted：继续阻塞独立数据库测试，重复准备完整镜像与服务。
- 直接把完整拓扑切换到托管执行器：缺少实际 KVM、Cube 和容量证据。
- 跳过 Cube 检查：无法证明公开运行链路。

## 后果

轻量测试无需外部 Cube 配置；完整系统任务使用托管执行器与本机 Cube，其环境和完整业务证据由[完整系统测试决定](2026-10-19-hosted-runtime-system-tests.md)维护。探针仅在自身相关路径修改或手动运行时执行，避免每次提交重复安装 Cube。

## 验证

验收以 GitHub 指定提交的实际 job 结果、真实数据库测试和沙盒产物字节为准。工作流选择器与环境边界由脚本回归测试及负控验证；完整系统结果由后续决定单独记录。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 托管执行器的兼容性结论逐层取证 | KVM、安装、模板、共享挂载 | hosted probe workflow | [39226790630](https://github.com/xerrors/Yuxi/actions/runs/39226790630) | KVM 禁止软件模拟回退；产物字节不符必须失败 | Passed，ubuntu-24.04 上真实 KVM 客体、临时 XFS、Cube 安装、正式模板、UID 1000 命令执行及宿主共享文件字节回读全部通过 |
| 独立测试不需要 Cube | 误依赖完整 API/worker | 独立测试选择器 | 实际 PostgreSQL 16、Redis 7.4.10，运行 CI 脚本 | Cube 与共享 API 地址不可达时仍执行全部选定用例 | Passed，本地脚本进程退出码 0；[远端 39225475784](https://github.com/xerrors/Yuxi/actions/runs/39225475784) 使用 Python 3.13.15，318 项全部通过、无 skip，测试耗时 201.99 秒 |
| 测试资源不会被本地部署配置替换 | 读取默认资源或 dotenv 覆盖 | CI 脚本 | `python3 -m unittest scripts.test_ci_resource_boundaries` | 省略各资源变量、部署 dotenv 存在、非托管执行器均拒绝；副作用命令使用隔离 shim | Passed |

托管探针在安装前准备与安装器配置一致的 CoreDNS 镜像，保留原有启动、DNS 和沙盒成功标准。[托管探针](https://github.com/xerrors/Yuxi/actions/runs/39226790630)验证该冷启动准备、Cube 安装与正式模板成功，真实沙盒文件从宿主回读通过；该结果只证明此次执行器的兼容性，不替代完整业务拓扑的容量和 E2E 证据。远端后端 unit [39225151544](https://github.com/xerrors/Yuxi/actions/runs/39225151544) 为 2999 passed；本地工程契约及相关脚本共 81 项、文档构建和相对链接检查通过。完整系统的托管迁移与完整 E2E 证据由[后续决定](2026-10-19-hosted-runtime-system-tests.md)维护，以上探针与独立集成结果不能替代该验证。
