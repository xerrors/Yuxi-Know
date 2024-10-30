<h1 style="text-align: center">语析 （基于大模型的知识图谱问答平台）</h1>



> [!NOTE]
> 当前项目还处于开发的早期，还存在一些 BUG，有问题随时提 issue。

## 概述

基于大模型 RAG 知识库与知识图谱的问答平台。Llamaindex + VueJS + Flask + Neo4j。大模型适配 OpenAI、国内主流大模型平台的模型调用、本地 vllm 部署。只需要配置对应服务平台的 `API_KEY` 即可使用。

![main](./images/main.png)


## 快速上手

在启动之前，提供 API 服务商的 API_KEY，并放置在 `src/.env` 文件中，参考 `src/.env.template`。默认使用的是智谱AI。需要配置 `ZHIPUAI_API_KEY=<ZHIPUAI_API_KEY>`。
本项目的基础对话服务可以在不含显卡的设备上运行，大模型使用在线服务商的接口。但是如果想要完整的知识库对话体验，则需要 8G 以上的显存。因为需要本地运行 embedding 模型和 rerank 模型。

**提醒**：下面的脚本会启动开发版本，源代码的修改会自动更新（含前端和后端）。如果生产环境部署，请使用 ` docker/docker-compose.yml` 启动。

```bash
docker-compose -f docker/docker-compose.dev.yml up --build
```

下面的这些容器都会启动：

```bash
[+] Running 7/7
 ✔ Network docker_app-network       Created
 ✔ Container graph-dev              Started
 ✔ Container milvus-etcd-dev        Started
 ✔ Container milvus-minio-dev       Started
 ✔ Container milvus-standalone-dev  Started
 ✔ Container api-dev                Started
 ✔ Container web-dev                Started
```

**预览**

![DEMO.GIF](./images/demo.gif)

关闭 docker 服务：

```bash
docker-compose -f docker/docker-compose.dev.yml down
```

查看日志：

```bash
docker logs <CONTAINER_NAME>  # 例如：docker logs api-dev
```

如果需要使用到本地模型，比如向量模型或者重排序模型，则需要将环境变量中设置的 `MODEL_ROOT_DIR` 做映射，比如本地模型都是存放在 `/hdd/models` 里面，则需要在 `docker-compose.yml` 和 `docker-compose.dev.yml`  中添加：

```yml
services:
  api:
    build:
      context: ..
      dockerfile: docker/api.Dockerfile
    container_name: api-dev
    working_dir: /app
    volumes:
      - ../src:/app/src
      - ../saves:/app/saves
      - /hdd/zwj/models:/hdd/zwj/models  # <== 修改这一行
```

**生产环境部署**：本项目同时支持使用 Docker 部署生产环境，只需要更换 `docker-compose` 文件就可以了。

```bash
docker-compose -f docker/docker-compose.yml up --build
```

## 更新日志

- 2024.10.12 后端修改为 [FastAPI](https://github.com/fastapi)，并添加了 [Milvus-Standalone](https://github.com/milvus-io) 的独立部署。

## 相关问题

### 镜像下载问题

如果无法直接下载相关镜像，参考 [DaoCloud/public-image-mirror](https://github.com/DaoCloud/public-image-mirror?tab=readme-ov-file#%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B)，尝试将前缀替换为：

```bash
# 以 neo4j 为例，其余一样
docker pull m.daocloud.io/docker.io/library/neo4j:latest

# 然后重命名镜像
docker tag m.daocloud.io/docker.io/library/neo4j:latest neo4j:latest
```
