# 快速开始指南

::: tip 提示
除了此文档网站外，小伙伴们还可以在 [Zread](https://zread.ai/xerrors/Yuxi-Know) 或 [DeepWiki](https://deepwiki.com/xerrors/Yuxi-Know) 平台查看自动生成的详细项目文档。
:::


## 快速开始


### 安装步骤

项目采用微服务架构，核心服务无需 GPU 支持。GPU 仅用于可选的 OCR 服务和本地模型推理，可通过环境变量配置外部服务。

#### 1. 获取项目代码

```bash
# 克隆稳定版本
git clone --branch v0.3.0 --depth 1 https://github.com/xerrors/Yuxi-Know.git
cd Yuxi-Know
```

::: warning 版本说明
- `v0.3.0`: 稳定版本
- `v0.3.0`：最新的 Beta 测试版
- `main`: 最新开发版本（不稳定，新特性可能会导致新 bug）
:::

#### 2. 配置环境变量

复制环境变量模板并编辑：

```bash
cp .env.template .env
```

编辑 `.env` 文件，配置必需的 API 密钥：


<<< @/../.env.template#model_provider{bash 2}


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

- **Web 界面**: `http://localhost:5173`
- **API 文档**: `http://localhost:5050/docs`

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
