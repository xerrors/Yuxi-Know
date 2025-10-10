# 快速开始指南



## 快速开始

::: tip 提示
项目采用微服务架构，核心服务无需 GPU 支持。GPU 仅用于可选的 OCR 服务和本地模型推理，可通过环境变量配置外部服务。
:::

### 安装步骤

#### 1. 获取项目代码

```bash
# 克隆稳定版本
git clone -b 0.2.1 https://github.com/xerrors/Yuxi-Know.git
cd Yuxi-Know
```

::: warning 版本说明
- `0.2.1`: 当前稳定版本（推荐）
- `stable`: 旧版本稳定分支（与现版本不兼容）
- `main`: 最新开发版本（可能不稳定）
:::

#### 2. 配置环境变量

复制环境变量模板并编辑：

```bash
cp src/.env.template src/.env
```

编辑 `src/.env` 文件，配置必需的 API 密钥：

```env
# 必需配置 - 推荐使用硅基流动免费服务
SILICONFLOW_API_KEY=sk-270ea********8bfa97.e3XOMd****Q1Sk
```

::: tip 免费获取 API Key
[硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) 注册即送 14 元额度，支持多种开源模型。
:::

#### 3. 启动服务

```bash
# 构建并启动所有服务
docker compose up --build

# 后台运行（推荐）
docker compose up --build -d
```

#### 4. 访问系统

服务启动完成后，访问以下地址：

- **Web 界面**: http://localhost:5173
- **API 文档**: http://localhost:5050/docs

#### 5. 停止服务

```bash
docker compose down
```

### 故障排除

#### 查看服务状态

```bash
# 查看所有容器状态
docker ps

# 查看后端服务日志
docker logs api-dev -f

# 查看前端服务日志
docker logs web-dev -f
```

#### 常见问题

<details>
<summary><strong>Docker 镜像拉取失败</strong></summary>

如果拉取镜像失败，可以尝试手动拉取：

```bash
bash docker/pull_image.sh python:3.11-slim
```

**离线部署方案**：

```bash
# 在有网络的环境保存镜像
bash docker/save_docker_images.sh  # Linux/macOS
powershell -ExecutionPolicy Bypass -File docker/save_docker_images.ps1  # Windows

# 传输到目标设备
scp docker_images_xxx.tar <user>@<dev_host>:<path_to_save>

# 在目标设备加载镜像
docker load -i docker_images_xxx.tar
```

</details>

<details>
<summary><strong>构建失败</strong></summary>

如果构建失败，通常是网络问题，可以配置代理：

```bash
export HTTP_PROXY=http://IP:PORT
export HTTPS_PROXY=http://IP:PORT
```

如果已配置代理但构建失败，尝试移除代理后重试。

</details>

<details>
<summary><strong>Milvus 启动失败</strong></summary>

```bash
# 重启 Milvus 服务
docker compose up milvus -d
docker restart api-dev
```

</details>


## 常见问题

### 服务管理

**Q: 如何查看后端服务日志？**

```bash
# 查看后端日志
docker logs api-dev -f

# 查看前端日志
docker logs web-dev -f

# 查看所有服务状态
docker ps
```

### OCR 服务

**Q: RapidOCR 模型未找到怎么办？**

确认以下文件存在：
- `MODEL_DIR` 指向的目录存在 `SWHL/RapidOCR`
- 包含 `PP-OCRv4` 下的 `det_infer.onnx` 和 `rec_infer.onnx` 文件

**Q: MinerU/PaddleX 健康检查失败？**

分别检查服务状态：
- MinerU: http://localhost:30000/health
- PaddleX: http://localhost:8080/

确认 GPU/驱动与 CUDA 版本匹配。

### 数据库连接

**Q: Milvus 启动失败？**

```bash
# 重启 Milvus 服务
docker compose up milvus -d
docker restart api-dev
```

**Q: Neo4j 连接问题？**

检查默认账户信息：
- 用户名: `neo4j`
- 密码: `0123456789`
- 管理界面: http://localhost:7474

