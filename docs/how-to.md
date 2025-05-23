### 如何优雅的拉取镜像？

使用 `bash docker/pull_image.sh python:3.12` 就可以。

### 如何配置本地大语言模型？

支持添加以 OpenAI 兼容模式运行的本地模型，可在 Web 设置中直接添加（适用于 vllm 和 Ollama 等）。

> [!NOTE]
> 使用 docker 运行此项目时，ollama 或 vllm 需监听 `0.0.0.0`

![本地模型配置](./images/custom_models.png)

### 如何配置本地向量模型与重排序模型

强烈建议测试阶段先使用硅基流动部署的 bge-m3（免费且无需修改）。其他模型配置参考 [src/static/models.yaml](src/static/models.yaml)。

对于**向量模型**和**重排序模型**，选择 `local` 前缀的模型会自动下载。如遇下载问题，请参考 [HF-Mirror](https://hf-mirror.com/) 配置。

要使用已下载的本地模型：

1. 在网页设置中添加映射，需要注意，如果是在 docker 里面前缀直接设置为 `/models`

![image](https://github.com/user-attachments/assets/ab62ea17-c7d0-4f94-84af-c4bab26865ad)

2. 将文件夹映射到 docker 内部

```yml
# docker-compose.yml

services:
  api:
    build:
      context: .
      dockerfile: docker/api.Dockerfile
    container_name: api-dev
    working_dir: /app
    volumes:
      - ./server:/app/server
      - ./src:/app/src
      - ./saves:/app/saves
      - ${MODEL_DIR}:/models <== 比如修改为 /hdd/models:models
    ports:

```

3. 重新启动项目

```bash
docker compose down
docker compose up --build -d
```

注：添加本地向量模型由于在 docker 内外的路径差异很大，因此建议参考前面的路径映射之后，也在这里添加。

```yaml
# src/static/models.yaml
  # 添加本地向量模型（所有 FlagEmbedding 支持的模型）
  local/BAAI/bge-m3:
    name: BAAI/bge-m3
    dimension: 1024
    # local_path: /models/BAAI/bge-m3，也可以在这里配置

  # 添加 OpenAI 兼容的向量模型
  siliconflow/BAAI/bge-m3:
    name: BAAI/bge-m3
    dimension: 1024
    url: https://api.siliconflow.cn/v1/embeddings
    api_key: SILICONFLOW_API_KEY

  # 添加 Ollama 模型
  ollama/nomic-embed-text:
    name: nomic-embed-text
    dimension: 768
```

### 如何配置 MinerU 抽取数据

在 PDF 数据处理中，可以选择配置 [MinerU](https://github.com/opendatalab/MinerU) 来实现更快速、更准确的 PDF 识别效果。

```yml
  mineru-api:
    build:
      context: scripts/mineru-api
      dockerfile: Dockerfile
    image: mineru-api:latest
    container_name: mineru-api
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    ports:
      - "5051:5051"
    networks:
      - app-network
    restart: unless-stopped
    command: python -m uvicorn app:app --host 0.0.0.0 --port 5051 --app-dir /app
```

如果要添加代理的话，可以添加 build args

```yml
  mineru-api:
    build:
      context: scripts/mineru-api
      dockerfile: Dockerfile
      args:
        http_proxy: http://宿主机IP:7890
        https_proxy: http://宿主机IP:7890
```