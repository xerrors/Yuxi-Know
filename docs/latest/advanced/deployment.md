# 生产部署指南

本指南介绍了如何在生产环境中部署 Yuxi-Know。

## 前置要求

- **Docker Engine** (v24.0+)
- **Docker Compose** (v2.20+)
- **NVIDIA Container Toolkit** (如果在生产环境使用 GPU 服务)

注意事项：

1. 生产环境和开发环境最好是两台独立的机器，不然会存在端口和资源的冲突问题。
2. 虽然名为“生产环境”，但实际上只是做了一些基本的配置而已，真要上线业务，需要根据实际情况进行调整。
3. 前端有个**调试面板**，长按侧边栏触发，生产环境不建议开启。

## 部署步骤

### 1. 配置环境变量

为了避免与开发环境的冲突，建议在生产环境中使用 `.env.prod` 文件。请确保你已经从模板创建了该文件并填写了必要的密钥。

```bash
cp .env.template .env.prod
```

编辑 `.env.prod` 文件，设置强密码并配置必要的 API 密钥：

- `NEO4J_PASSWORD`: 修改默认密码
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`: 修改默认密钥
- `SILICONFLOW_API_KEY` 等模型密钥

### 2. 启动服务

使用 `docker-compose.prod.yml` 文件启动生产环境：

```bash
# 仅启动核心服务 (CPU 模式)
docker compose -f docker-compose.prod.yml up -d --build

# 启动所有服务 (包含 GPU OCR 服务)
docker compose -f docker-compose.prod.yml --profile all up -d --build
```

### 3. 验证部署

- **Web 访问**: `http://localhost` (直接通过 80 端口访问，无需 :5173)
- **API 健康检查**: `curl http://localhost/api/system/health`

## 维护与更新

### 更新代码并重新部署

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker compose -f docker-compose.prod.yml up -d --build
```

### 查看日志

```bash
# 查看 API 日志
docker logs -f api-prod

# 查看 Nginx 访问日志
docker logs -f web-prod
```
