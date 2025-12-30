# 常见问题

以下为最常见的安装与使用问题，更多细节请参阅相应章节链接。

## Docker与启动相关问题

### 镜像拉取/构建失败？
镜像拉取：可使用以下脚本辅助拉取
- **Linux/macOS**: `docker/pull_image.sh`
- **Windows PowerShell**: `docker/pull_image.ps1`
构建失败：若配置了代理仍失败，可尝试以下步骤：
1. 注释 `api.Dockerfile` 中的代理环境变量设置：
   ```dockerfile
   # 注释掉以下代理配置
   # ENV HTTP_PROXY=$HTTP_PROXY \
   #     HTTPS_PROXY=$HTTPS_PROXY \
   #     http_proxy=$HTTP_PROXY \
   #     https_proxy=$HTTPS_PROXY
   ```
2. 注释 `docker-compose.yml` 中的代理构建参数：
   ```yaml
   services:
     api:
       build:
         context: .
         dockerfile: docker/api.Dockerfile
         # 注释掉代理构建参数
         # args:
         #   HTTP_PROXY: ${HTTP_PROXY:-}
         #   HTTPS_PROXY: ${HTTPS_PROXY:-}
   ```
3. 在 `api.Dockerfile` 中添加国内镜像源加速依赖安装：
   ```dockerfile
   RUN --mount=type=cache,target=/root/.cache/uv \
       uv sync --no-dev --index-url https://pypi.tuna.tsinghua.edu.cn/simple
   ```


### 服务启动失败？
- 检查端口占用情况：使用 `lsof -i :5050` 或 `netstat -tuln | grep 5050` 查看端口使用
- 确认 Docker 服务状态：`systemctl status docker`（Linux）或 `Docker Desktop` 应用状态（Windows/macOS）
- 参考日志定位问题：`docker logs --tail=100 api-dev`、`docker logs --tail=100 web-dev`

### 服务端口与访问地址？
- Web: `http://localhost:5173`；API 文档: `http://localhost:5050/docs`

### Milvus/Neo4j 启动或连接失败？
- 重启：`docker compose up milvus -d && docker restart api-dev`
- Neo4j 默认：用户名 `neo4j`、密码 `0123456789`、管理界面 `http://localhost:7474`
- Milvus 检查：`docker logs milvus -f` 查看启动状态

### 首次运行如何创建管理员？
- Web 首次启动会引导初始化；也可调用 API：
  - `GET /api/auth/check-first-run` → `first_run=true` 时
  - `POST /api/auth/initialize` 提交 `user_id` 与 `password`
- 无默认账号，初始化后使用创建的超级管理员登录

### 如何查看日志和状态？
- `docker ps` 查看整体服务状态
- `docker logs api-dev -f`、`docker logs web-dev -f` 查看实时服务日志
- `docker compose logs --tail=100` 查看所有服务日志

## 其他常见问题

### OCR 模型或服务不可用？
  - RapidOCR 本地模型：确保 `MODEL_DIR/SWHL/RapidOCR` 下存在 `PP-OCRv4` 模型
  - MinerU/PP-StructureV3：检查健康检查接口与 GPU/CUDA 版本

### 登录失败被锁定？
  - 多次失败会临时锁定账户，请根据提示等待后重试
