---
name: 提交一个启动问题
about: Docker镜像拉取、服务启动、端口占用等相关问题
title: 'Startup: '
labels: startup
assignees: ''

---

## 1️⃣ 问题描述

请清晰描述您在使用 Docker 或启动服务时遇到的问题：
- 操作步骤：您执行了什么操作？
- 预期结果：您期望看到什么？
- 实际结果：实际发生了什么？

例如："执行 `docker compose up -d` 后，api-dev 服务一直重启，查看日志显示无法连接到 Milvus"

您可以先看一下常见问题与解决方案：https://xerrors.github.io/Yuxi-Know/latest/changelog/faq.html


## 2️⃣ 环境信息

请提供以下信息，帮助我们快速定位问题：
- 操作系统：Windows/macOS/Linux 及版本
- Docker 版本：执行 `docker --version` 输出
- Docker Compose 版本：执行 `docker compose --version` 输出
- 项目版本：执行 `git rev-parse HEAD` 输出


## 3️⃣ 启动命令

请提供您使用的完整启动命令：
```bash
# 例如
docker compose up -d
# 或
make start
```


## 4️⃣ 日志信息

请提供相关服务的日志（至少包含最近 100 行）：

```bash
# 查看所有服务状态
docker ps

# 查看 api-dev 服务日志
docker logs --tail=100 api-dev

# 查看所有服务日志
docker compose logs --tail=100
```

将日志粘贴到下方（可根据问题相关性选择部分日志）：

```
# api-dev 日志
...

# 其他相关服务日志
...
```


## 5️⃣ 配置文件（可选）

如果您修改过 `docker-compose.yml` 或 `.env` 文件，请提供相关配置片段（注意隐藏敏感信息）：

```yaml
# docker-compose.yml 相关部分
...

# .env 相关部分
...
```


## 6️⃣ 其他信息

您还可以提供以下信息帮助我们解决问题：
- 是否已尝试过重启 Docker 服务？
- 是否已清理过 Docker 缓存或旧容器？
- 网络环境是否有特殊配置（如代理、防火墙等）？
- 是否有其他相关的错误提示或截图？
