# 常规运行链路 CI 使用 container 沙盒

状态：implemented
类型：process
Owner：.github/workflows/system-tests.yml

## 问题

常规系统测试的两个 job 都安装 KVM、Cube 和正式用户模板，业务回归因此依赖 VM 环境准备。仓库已有 container 后端、独立 runner、真实 Docker 隔离测试和 API/worker 执行测试，可以在不安装 Cube 的托管执行器上证明应用链路。

## 决策

### 实现方案

`system-tests.yml` 的两个 job 使用现有 Compose `container` profile。环境准备脚本生成临时状态目录和 runner 认证令牌，镜像构建脚本增加正式 sandbox 镜像与缓存。保留原有后台作业、readiness、持久化、权限和确定性 Agent 验证，沙盒专项改为已有 container HTTP/worker E2E 与宿主真实 Docker 隔离测试。API 和 worker 继续不持有 Docker socket。

协作 E2E 对 container 使用同一 Project 的真实文件作为父子 Run 的 execute 探针，并在压缩后回读文件、等待终态容器清理；对 Cube 保留持久 VM 的 `/tmp` 和执行身份断言。显式选择的 container 专项在服务报告错误后端时失败，不能用 skip 冒充通过。

`cube-hosted-probe.yml` 仅保留手动入口；Cube 实现、单测、专属 integration/E2E 与生产默认后端不变。常规 CI 的成功不表达 Cube VM、模板或共享挂载已通过验证。此决定部分取代[托管系统测试](2026-10-19-hosted-runtime-system-tests.md)、[托管资源边界](2026-10-19-hosted-ci-resource-boundaries.md)与[沙盒环境](2026-10-15-sandbox-environment.md)中常规 CI 选择 Cube 的部分。

## 替代方案

- 保留自动 Cube 安装：验证范围包含 VM，但每个系统 job 继续支付环境准备成本。
- 仅删除 Cube 步骤或跳过沙盒测试：无法证明真实命令执行、隔离和终态清理。
- 修改产品默认后端：超出 CI 范围，也不能替代明确的 CI 装配。

## 后果

container 与 Cube VM 具有不同的隔离和临时目录语义。常规 CI 验证真实 Docker 的执行、文件与清理，不证明 Cube 模板或 VM 兼容性；需要时由维护者手动运行探针及 Cube 专属测试。两个系统 job 各自持有完整拓扑，保留后台恢复的停止/重建边界，互不停止对方服务。冷构建仍依赖镜像仓库和网络。

## 验证

- Passed：`python3 -m unittest scripts.test_ci_resource_boundaries scripts.test_verify_engineering_contracts scripts.test_release_workflows`，86 项。真实 Compose 展开确认两种业务进程使用 container、令牌与挂载匹配、socket 仅归 runner；恢复 Cube、遗漏 runner/镜像、修改探针事件或关闭专项标记均被负控拒绝。实际 shell 的构建参数测试核对 sandbox 镜像及独立缓存，遗漏 profile 时构建前失败。
- Passed：后端全量 `pytest test/unit -m "not slow" -q` 为 3104 passed、107 skipped；容器未挂载仓库根文件的部署检查另在宿主执行。后端 support unit 31 项，覆盖 Project 与 `/tmp` 两类重放探针及错误后端不能 skip；部署配置 unit 174 项，继续验证生产默认契约。
- Passed：真实 Docker container integration 26 项，无 skip。使用预构建 sandbox 镜像，显式设置 `SANDBOX_CONTAINER_TEST=1`，执行 `uv run --project backend --no-sync --group test pytest backend/test/integration/sandbox/test_container_sandbox.py -q`，通过 Docker inspect、文件字节、进程及协议证明隔离、认证、取消和清理。
- Passed：独立 Compose container 拓扑执行工作流的 readiness 与 worker 基线检查，包含暂停 worker 后 readiness 失效与恢复、3 项 readiness API，以及 2 项 container execute/steer E2E，无 skip。E2E 回读 Viewer 文件、Run 终态、执行身份及无活动容器状态。
- Passed：工作流原有确定性生命周期入口 `bash backend/test/run_tests.sh e2e`，41 项、无 skip，包含 FIFO、steer、审批、取消、消费进程丢失恢复、五组父子协作、容量控制、停止和深度拒绝；协作分支回读 Project 文件与持久结果。
- Passed：工作流后台作业阶段通过停止 API/worker、保存未发布 intent、启动正式 worker、回读领域结果，3 项跨阶段服务测试与 10 项作业/暂存/图谱 HTTP 测试通过。
- Passed：其余 23 个保留的系统检查步骤通过，其中 pytest 共 203 项，覆盖附件对象、MCP 故障、权限撤销、Skill 恢复、知识检索及持久化事务，另包含 OIDC 代理静态检查。最后的 Search/Fetch worker E2E 1 项通过，使用正式 Compose overlay、TLS 重放服务并回读 worker 结果。
- Passed：工程契约检查、Shell 语法、YAML 解析、后端源码及修改测试的 Ruff 检查、docs build 与 `git diff --check`。
- Not run：GitHub 托管执行器上的完整两个 job、镜像冷构建及缓存上传、真实 Cube。本地验证复用同一 Dockerfile 已构建的镜像，挂载当前源码与测试，并使用独立状态、账号、端口和网络；本地结果不能写成 GitHub Actions 已通过。
