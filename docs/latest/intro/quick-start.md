# 快速开始指南

::: tip 提示
除了此文档网站外，用户还可以在 [Zread](https://zread.ai/xerrors/Yuxi-Know) 或 [DeepWiki](https://deepwiki.com/xerrors/Yuxi-Know) 平台查看自动生成的详细项目文档。
:::


## 快速开始


### 安装步骤

项目采用微服务架构，核心服务无需 GPU 支持。GPU 仅用于可选的 OCR 服务和本地模型推理，可通过环境变量配置外部服务。

#### 1. 获取项目代码

```bash
# 克隆稳定版本
git clone --branch v0.4.3 --depth 1 https://github.com/xerrors/Yuxi-Know.git
cd Yuxi-Know
```

::: warning 版本说明
- `v0.4.3`: 稳定版本
- `main`: 最新开发版本（不稳定，新特性可能会导致新 bug）
:::

#### 2. 项目启动

**方法 1**：使用 init 脚本（推荐）

我们提供了自动化的初始化脚本，可以帮您完成环境配置和 Docker 镜像拉取：

```bash
# Linux/macOS
./scripts/init.sh

# Windows PowerShell
.\scripts\init.ps1
```

脚本会：
- 检查并创建 `.env` 文件
- 提示您输入 `SILICONFLOW_API_KEY`（必需）
- 提示您输入 `TAVILY_API_KEY`（可选，用于搜索服务）
- 自动拉取所有必需的 Docker 镜像

::: tip API Key 获取
- [硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) 注册即送 14 元额度
- [Tavily](https://app.tavily.com/) 获取搜索服务 API Key（可选）
:::

**方法 2**：手动配置环境变量

复制环境变量模板并编辑：

```bash
cp .env.template .env
```

编辑 `.env` 文件，配置必需的 API 密钥，这里强烈建议先使用硅基流动的 API 和模型（DeepSeek）验证平台的功能无误后，再尝试切换到自己的模型：


<<< @/../.env.template#model_provider{bash 5}


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

**注意**：启动后，可能还需要一些时间，尤其是后端服务需要一段时间，请耐心等待 2-3 分钟。

#### 4. 访问系统

服务启动完成后，访问以下地址：

- **Web 界面**: `http://localhost:5173`
- **API 文档**: `http://localhost:5050/docs`

#### 5. 停止服务

```bash
docker compose down
```

## 对话

项目第一次启动后，会要求填写超级管理员账号和密码，请确保填写正确。

然后在智能体页面可以进行对话，在右侧可以配置提示词、模型、工具等参数。

![agent.png](/images/agent.png)



## 故障排除

::: tip 调试面板
前端有个**调试面板**，长按侧边栏空白处触发，生产环境建议删除此特性，在 `AppLayout.vue` 中注释掉相关代码。
:::

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
# Linux/macOS
bash docker/pull_image.sh python:3.12-slim

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File docker/pull_image.ps1 python:3.12-slim
```

**离线镜像拉取方案**：

```bash
# 在有网络的环境保存镜像（镜像名称需要确认是否和实际一致）
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
# Linux / macOS
export HTTP_PROXY=http://IP:PORT
export HTTPS_PROXY=http://IP:PORT

# Windows PowerShell
$env:HTTP_PROXY="http://IP:PORT"
$env:HTTPS_PROXY="http://IP:PORT"
```

如果已配置代理但构建失败，尝试移除代理后重试。

如果出现，FetchError: request to https://registry.npmjs.org/npm failed, reason: connect ECONNREFUSED 127.0.0.1:7890

新建一个终端重新执行，并确保没有代理干扰。

</details>

<details>
<summary><strong>Milvus 启动失败</strong></summary>

```bash
# 重启 Milvus 服务
docker compose up milvus -d
docker restart api-dev
```

</details>
