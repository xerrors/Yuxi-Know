# Kubernetes 沙盒配置

Yuxi-Know 现在支持 `sandbox_mode = "k8s"`。

## 架构

- 主应用通过 `src/sandbox/k8s_sandbox.py` 按 `thread_id` 懒加载沙盒
- `K8sSandboxProvider` 通过 provisioner 服务创建 / 查询 / 删除沙盒
- provisioner 通过 Kubernetes API 管理 `Pod + Service`
- 沙盒运行时通过 HTTP API 提供：
  - `POST /exec`
  - `POST /files/read`
  - `POST /files/write`
  - `POST /files/list`

## 主应用配置

可通过配置文件或环境变量设置：

```toml
sandbox_mode = "k8s"
sandbox_k8s_provisioner_url = "http://sandbox-provisioner:8002"
sandbox_k8s_request_timeout_seconds = 30.0
```

对应环境变量：

```bash
export SANDBOX_MODE=k8s
export SANDBOX_K8S_PROVISIONER_URL=http://sandbox-provisioner:8002
export SANDBOX_K8S_REQUEST_TIMEOUT_SECONDS=30
```

## Provisioner 环境变量

Provisioner 自身尽量承载部署细节，最小需要：

- `SANDBOX_K8S_NAMESPACE`：目标 namespace，默认 `yuxi-sandbox`
- `SANDBOX_RUNTIME_IMAGE`：沙盒运行时镜像
- `SANDBOX_RUNTIME_PORT`：运行时 HTTP 端口，默认 `8080`
- `SANDBOX_K8S_READY_TIMEOUT_SECONDS`：等待 Pod Ready 的超时秒数

可选资源限制：

- `SANDBOX_K8S_CPU_REQUEST`
- `SANDBOX_K8S_CPU_LIMIT`
- `SANDBOX_K8S_MEMORY_REQUEST`
- `SANDBOX_K8S_MEMORY_LIMIT`

## 集群前提

需要为 provisioner 提供以下能力：

- 可访问 Kubernetes API（kubeconfig 或 in-cluster config）
- 目标 namespace 的 `get/list/create/delete/watch` 权限：
  - Pods
  - Services
- 可拉取沙盒运行时镜像

## 生命周期

- 同一 `thread_id` 在一次 agent 执行期间只会 provision 一次
- agent 结束后，`src/sandbox/middleware.py` 会按同一个 `thread_id` 调用 release
- release 会删除远端 `Pod + Service`

## 手动验证

1. 启动 provisioner 服务
2. 设置：
   - `SANDBOX_MODE=k8s`
   - `SANDBOX_K8S_PROVISIONER_URL=...`
3. 触发一次 sandbox 工具调用：`bash` / `write_file` / `read_file` / `ls`
4. 确认：
   - 集群中创建了对应 Pod + Service
   - `/workspace` 可读写
   - agent 结束后资源被删除
