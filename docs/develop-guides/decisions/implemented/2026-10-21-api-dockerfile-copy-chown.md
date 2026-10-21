# API 镜像 COPY 显式运行时属主

状态：implemented
类型：bug-fix
Owner：docker/api.Dockerfile

## 问题

Issue #1109：构建上下文中的应用文件若为 `0600` 等严格权限，`COPY` 默认以 root 写入镜像后，容器以 `USER 1000:1000` 运行时无法读取 `/app/pyproject.toml` 或监听 `/app/server`。

## 决策

### 实现方案

对 `pyproject.toml`、`.python-version`、`uv.lock`、`package`、`server` 与入口脚本的 `COPY` 使用 `--chown=1000:1000`。`uv sync` 之后在创建运行用户的 `RUN` 中再次 `chown` `/app/package`，覆盖同步可能产生的 root 属主文件。`/app/runtime` 与 `$HOME` 仍由该 `RUN` 创建并赋权。

## 替代方案

仅在 `USER` 前对整个 `/app` 做 `chown -R`：能修复属主，但不满足「COPY 时显式指定所有权」的构建契约，且更容易漏掉后续新增的 `COPY`。保持无 `--chown`：在 Linux 严格 umask 或保留权限位的构建环境中会复现启动失败。

## 后果

镜像层中应用文件属主为 uid/gid 1000；root 构建步骤仍可读写这些路径。开发 Compose 的 bind mount 仍反映宿主权限，不在本决定范围内。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 应用 COPY 均带 `--chown=1000:1000` | 漏改某一 COPY | api.Dockerfile | unit：`test_api_dockerfile_copy_app_content_with_runtime_uid` | 去掉 pyproject.toml 的 `--chown` 后 guard 失败 | Passed |
| 严格权限位下 uid 1000 可读 | 仅改测试不改镜像 | api.Dockerfile | 临时目录多阶段 Dockerfile：`alpine` 写入 `0600` 文件后 `COPY`（无 `--chown`）再 `USER 1000` → `cat: Permission denied`；同内容加 `COPY --chown=1000:1000` → 可读。命令：`docker build --no-cache -t yuxi-1109-probe:broken <tmpdir>` / `docker run --rm yuxi-1109-probe:broken` 与对应 `:fixed` 镜像 | 无 `--chown` 探针 | Passed |

- Passed：`python -m pytest backend/test/unit/config/test_docker_compose_service_boundaries.py -k "dockerfile_copy or owner_only_umask" --noconftest -q`（3 项）；`python scripts/verify_engineering_contracts.py`；上述 Docker 探针（broken/fixed）。
