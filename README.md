![Yuxi：可私有部署的知识智能体平台](https://xerrors.oss-cn-shanghai.aliyuncs.com/posts/2026/08/20260818-151118-mac-1787037059154-8c08f48c.png)

Yuxi（语析）是一个可私有部署的知识智能体平台，面向需要管理数据、模型和团队权限的组织。用户可以检索内部资料、配置智能体、通过工具和协作会话执行任务，并在持久工作区中查看和下载文件产物。

[项目主页](https://xerrors.github.io/Yuxi/) · [快速开始](https://xerrors.github.io/Yuxi/intro/quick-start) · [演示视频](https://www.bilibili.com/video/BV1erE26iEgv/) · [版本记录](https://github.com/xerrors/Yuxi/releases) · [English](README.en.md)


[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=ffffff)](https://github.com/xerrors/Yuxi/blob/main/docker-compose.yml)
[![Release](https://img.shields.io/github/v/release/xerrors/Yuxi?color=046A82)](https://github.com/xerrors/Yuxi/releases/latest)
[![License](https://img.shields.io/github/license/xerrors/Yuxi.svg?logo=github)](https://github.com/xerrors/Yuxi/blob/main/LICENSE)
[![DeepWiki](https://img.shields.io/badge/DeepWiki-blue.svg)](https://deepwiki.com/xerrors/Yuxi)
[![Bilibili](https://img.shields.io/badge/知识库演示-00A1D6?logo=bilibili&logoColor=fff)](https://www.bilibili.com/video/BV1erE26iEgv/)

<a href="https://trendshift.io/repositories/24335" target="_blank"><img src="https://trendshift.io/api/badge/repositories/24335" alt="xerrors%2FYuxi | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

## Yuxi 能做什么

| 能力 | 当前范围 |
| --- | --- |
| 知识库与 RAG | 上传、解析和索引文档，配置嵌入与重排模型，测试检索和评估质量；飞书、Dify、Notion 提供只读连接器 |
| 知识图谱 | 管理员对已索引的 Milvus 文档块提交构建任务，将实体和关系写入 Neo4j，并与文本检索融合 |
| 智能体与协作 | 配置模型、提示词、Tools、MCP 和 Skills；协作会话拥有独立上下文，共享项目文件 |
| 文件与执行环境 | 每个用户使用持久 Cube VM，智能体在授权目录中读写文件、运行命令，产物支持预览和下载 |
| 团队与权限 | 管理用户、部门和共享资源范围；API Key 为外部应用提供独立 APP 与终端用户作用域 |
| 接入与观测 | Web、npm CLI 和公开 API 共用运行链路；提供后台作业、运行审计、Langfuse tracing 和用户反馈 |

默认审批模式要求确认命令执行和当前 Project 外的文件写入，Project 内写入自动放行；用户可选择完全信任模式。知识库检索评估由平台提供，完整智能体评估可通过公开 API 自行构建，见[智能体评估](docs/agents/agent-evaluation.md)。


## 赞助商

| 赞助商 | 介绍 |
| :---: | :--- |
| <img src="https://xerrors.oss-cn-shanghai.aliyuncs.com/github/%E4%B8%8B%E8%BD%BD.jpeg" alt="Fluxion AI LOGO" width="180" /> | Fluxion AI面向个人开发者、技术团队与企业，通过统一API接入并管理全球主流AI模型；通过多线路动态调度提升可用性，模型表现、响应时间与费用透明可查。根据不同模型与线路，API调用成本较官方或基准价格可降低40%—98%。专属链接[注册](https://fluxionai.space/register?source=github&campaign=yuxi&promo=YUXI) 获 $7 API 额度 |

## 快速启动

语析（Yuxi）的应用服务通过 Docker Compose 启动，Agent 执行环境使用专用 Linux/KVM 节点上的 Cube 用户 VM。

### 前置条件

安装 [Docker Engine](https://docs.docker.com/get-docker/) 和 Docker Compose，准备一个可用的大模型 API，并按[沙盒配置与运维](docs/advanced/sandbox-operations.md#原生执行节点)配置 Cube 节点、用户模板与共享目录。macOS/Windows 上运行应用也需要可访问的 Linux/KVM 节点。

当前候选源码版本为 `v0.8.0.beta1`，从 fork 的 `develop/0-8-0` 分支获取，tag 在验收后创建。0.8 仅面向全新部署，旧数据库、索引和文件布局不提供自动升级；请用独立数据目录试用，见[0.8.0 更新说明](docs/develop-guides/releases/0.8.0.md)。

### 1. 获取代码并初始化

```bash
git clone --branch develop/0-8-0 --depth 1 https://github.com/Yuchuan925/Yuxi.git
cd Yuxi

# Linux/macOS
./scripts/init.sh

# Windows PowerShell
.\scripts\init.ps1
```

初始化脚本创建 `.env`、读取 SiliconFlow API Key，并为 JWT 与 API Key 派生生成独立安全密钥。也可以手动复制 `.env.template`。脚本不部署 Cube 节点；还需填写 `CUBE_API_URL`、`CUBE_PROXY_NODE_IP`、`CUBE_NODE_USER_DATA_DIR` 和 `CUBE_NODE_SKILL_PROJECTION_DIR`，控制面启用认证时填写 `CUBE_API_KEY`。启动前运行 `docker compose config --quiet` 检查配置，完整步骤见[快速开始](docs/intro/quick-start.md)。

### 2. 启动开发环境

```bash
docker compose up --build -d
```

查看服务状态：

```bash
docker compose ps
curl --fail http://localhost:5050/api/system/ready
```

返回的 `status` 为 `ready` 后，打开 [http://localhost:5173](http://localhost:5173)，按页面提示初始化超级管理员并登录。API 文档位于 [http://localhost:5050/docs](http://localhost:5050/docs)。

## 文档导航

- [项目介绍](https://xerrors.github.io/Yuxi/intro/project-overview)：了解能力、概念和系统边界。
- [快速开始](https://xerrors.github.io/Yuxi/intro/quick-start)：从零启动本地环境。
- [命令行工具](docs/intro/cli.md)：登录实例、对话、发送附件和查询知识库。
- [公开 Agent API 入门](docs/intro/agents-api-quickstart.md)：外部应用创建会话、提交消息和读取结果。
- [模型配置](https://xerrors.github.io/Yuxi/intro/model-config)：接入聊天、嵌入和重排模型。
- [知识库教程](https://xerrors.github.io/Yuxi/intro/knowledge-base)：创建知识库并验证检索。
- [智能体开发](https://xerrors.github.io/Yuxi/agents/agents-config)：配置 Agent、工具和扩展。
- [生产部署](https://xerrors.github.io/Yuxi/advanced/deployment)：部署、升级、备份和排障。
- [版本变更记录](https://xerrors.github.io/Yuxi/develop-guides/changelog)：查看已发布变更。

## 界面预览

<details>
<summary>查看工作台、知识库、图谱、智能体配置、文件和团队管理截图</summary>

**智能体工作台**：查看回答、工具过程、协作任务和文件交付。

![智能体工作台](https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260825145022410.png)

**知识库**：管理文档处理、检索测试与评估。

![知识库](https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260830144756161.png)

**知识图谱**：构建实体和关系，查询关联子图。

![知识图谱](https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260830145027082.png)

**智能体配置**：选择模型、提示词、工具、MCP 和 Skills。

![智能体配置](https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260825151729055.png)

**工作区文件**：预览受支持的 HTML、PDF、Markdown、图片和代码，下载任务产物。

![工作区文件](https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260826202142495.png)

**团队管理**：管理用户、部门和共享资源范围。

![用户与部门管理](https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260826201638124.png)

</details>

## 参与贡献

欢迎提交 Issue、改进文档、修复 Bug 和贡献功能。开发流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，完整规范见 [文档参与指南](docs/develop-guides/contributing.md)。

感谢所有贡献者的支持！

<a href="https://github.com/xerrors/Yuxi/contributors">
  <img src="https://contrib.rocks/image?repo=xerrors/Yuxi&max=100&columns=10" />
</a>

---

## 许可证

Yuxi 本体采用 MIT License，详见 [LICENSE](LICENSE)。Docker Compose 引入的第三方组件遵循各自的许可证；再分发和商业部署前，请按实际镜像版本核对上游许可和源码义务，相关边界见[生产部署指南](docs/advanced/deployment.md)。

Yuxi 的实现和文档参考了以下优秀的开源项目：

- [LightRAG](https://github.com/HKUDS/LightRAG)：早期图谱构建和检索思路；
- [DeepAgents](https://github.com/langchain-ai/deepagents)：深度智能体框架；
- [DeerFlow](https://github.com/bytedance/deer-flow)：沙盒智能体架构思路；
- [RAGFlow](https://github.com/infiniflow/ragflow)：文档分块策略；
- [LangGraph](https://github.com/langchain-ai/langgraph)：智能体编排基础；
- [QwenPaw](https://github.com/agentscope-ai/QwenPaw)：模型配置和个人文件区域设计。

## Star History

<a href="https://www.star-history.com/?repos=xerrors%2Fyuxi&type=date&legend=bottom-right">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=xerrors/yuxi&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=xerrors/yuxi&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=xerrors/yuxi&type=date&legend=top-left" />
 </picture>
</a>


[![给 Yuxi 一个 Star](https://xerrors.oss-cn-shanghai.aliyuncs.com/posts/2026/08/20260818-184409-image-da91658b.png)](https://github.com/xerrors/Yuxi)
