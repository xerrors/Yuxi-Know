![Yuxi: a self-hosted knowledge agent platform](https://xerrors.oss-cn-shanghai.aliyuncs.com/posts/2026/08/20260818-151118-mac-1787037059154-8c08f48c.png)

Yuxi is a self-hosted knowledge agent platform for teams that manage their own data, models, and access policies. Users can retrieve internal documents, configure agents, execute tasks through tools and cooperating sessions, and preview or download files from persistent workspaces.

[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=ffffff)](https://github.com/xerrors/Yuxi/blob/main/docker-compose.yml)
[![Release](https://img.shields.io/github/v/release/xerrors/Yuxi?color=046A82)](https://github.com/xerrors/Yuxi/releases/latest)
[![License](https://img.shields.io/github/license/xerrors/Yuxi.svg?logo=github)](https://github.com/xerrors/Yuxi/blob/main/LICENSE)
[![DeepWiki](https://img.shields.io/badge/DeepWiki-blue.svg)](https://deepwiki.com/xerrors/Yuxi)
[![Bilibili](https://img.shields.io/badge/Knowledge_Base_Demo-00A1D6?logo=bilibili&logoColor=fff)](https://www.bilibili.com/video/BV1erE26iEgv/)

<a href="https://trendshift.io/repositories/24335" target="_blank"><img src="https://trendshift.io/api/badge/repositories/24335" alt="xerrors%2FYuxi | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[Project home](https://xerrors.github.io/Yuxi/) · [Quick start](https://xerrors.github.io/Yuxi/intro/quick-start) · [Demo video](https://www.bilibili.com/video/BV1erE26iEgv/) · [Releases](https://github.com/xerrors/Yuxi/releases) · [中文](README.md)

## What Yuxi Can Do

| Capability | Current scope |
| --- | --- |
| Knowledge bases and RAG | Upload, parse, and index documents; configure embedding and rerank models; use vector, BM25, or hybrid retrieval and verify sources; connect external knowledge sources for read-only access |
| Knowledge graphs | Administrators submit build jobs for indexed Milvus chunks, store entities and relationships in Neo4j, and combine graph and text retrieval |
| Agents and cooperation | Configure models, prompts, tools, MCP, and Skills; cooperating sessions keep independent contexts and share project files |
| Files and execution | Each user has a persistent Cube VM for authorized file operations and commands, with artifact previews and downloads |
| Team access | Manage users, departments, and shared resource scopes; API Keys isolate external applications and their end users |
| Integration and observation | Web, npm CLI, and Public API share the execution pipeline; knowledge bases support read-only MCP access, with background jobs, execution audits, Langfuse tracing, and feedback |

The default approval mode requires confirmation for command execution and file writes outside the current Project; writes inside it proceed automatically. Users can select the always-trust mode. The platform evaluates knowledge retrieval; complete agent evaluators can be built through the Public API as described in [agent evaluation](docs/agents/agent-evaluation.md).

## Tech Stack

| Layer | Technologies |
| --- | --- |
| Frontend | Vue 3 · Vite · Ant Design · G6 |
| Backend | FastAPI · LangGraph · ARQ worker |
| Storage | PostgreSQL · Redis · MinIO · Milvus · Neo4j |
| Document processing | MinerU · PaddleX · RapidOCR |
| Deployment | Docker Compose |

## Quick Start

### Prerequisites

Install [Docker Engine](https://docs.docker.com/get-docker/) and Docker Compose, prepare a working LLM API, and configure a dedicated Linux/KVM Cube node, user template, and shared Workspace/Skills directories as described in [sandbox operations](docs/advanced/sandbox-operations.md). Applications running on macOS or Windows also need access to this Linux/KVM node.

The candidate source version is `v0.8.0.beta2`, available from the main repository's `develop/0-8-0` branch; the tag is created after validation. Version 0.8 requires a fresh deployment with separate data directories and provides no automatic upgrade of older databases, indexes, or file layouts. See the [0.8.0 release notes](docs/develop-guides/releases/0.8.0.md).

### 1. Get the Code and Initialize

```bash
git clone --branch develop/0-8-0 --depth 1 https://github.com/xerrors/Yuxi.git
cd Yuxi

# Linux/macOS
./scripts/init.sh

# Windows PowerShell
.\scripts\init.ps1
```

The initialization script creates `.env`, prompts for a SiliconFlow API Key, and generates separate JWT and API Key derivation secrets. You can also copy `.env.template` manually. It does not provision Cube: configure `CUBE_API_URL`, `CUBE_PROXY_NODE_IP`, `CUBE_NODE_USER_DATA_DIR`, and `CUBE_NODE_SKILL_PROJECTION_DIR`, plus `CUBE_API_KEY` when the node requires authentication. Run `docker compose config --quiet` before starting. See the [quick start](docs/intro/quick-start.md) for the complete steps.

### 2. Start the Development Environment

```bash
docker compose up --build -d
```

Check service status:

```bash
docker compose ps
curl --fail http://localhost:5050/api/system/ready
```

Once the returned `status` is `ready`, open [http://localhost:5173](http://localhost:5173), follow the page instructions to initialize the superadmin account, and sign in. API documentation is available at [http://localhost:5050/docs](http://localhost:5050/docs).

Keep the existing deployment and a consistent backup of PostgreSQL, MinIO, and user files before trying 0.8 in a separate environment. Read the [production deployment guide](docs/advanced/deployment.md) for the current schema and storage requirements.

## Documentation

- [Project overview](https://xerrors.github.io/Yuxi/intro/project-overview): Capabilities, concepts, and system boundaries.
- [Quick start](https://xerrors.github.io/Yuxi/intro/quick-start): Set up a local environment from scratch.
- [Command-line client](docs/intro/cli.md): Sign in, chat, send attachments, and query knowledge bases.
- [Public Agent API quick start](docs/intro/agents-api-quickstart.md): Create sessions, submit messages, and read results from external applications.
- [Model configuration](https://xerrors.github.io/Yuxi/intro/model-config): Connect chat, embedding, and rerank models.
- [Knowledge base tutorial](https://xerrors.github.io/Yuxi/intro/knowledge-base): Create knowledge bases and verify retrieval.
- [Agent development](https://xerrors.github.io/Yuxi/agents/agents-config): Configure agents, tools, and extensions.
- [Production deployment](https://xerrors.github.io/Yuxi/advanced/deployment): Deployment, upgrades, backups, and troubleshooting.
- [Changelog](https://xerrors.github.io/Yuxi/develop-guides/changelog): Published changes.

## Screenshots

<details>
<summary>View the workspace, knowledge bases, graphs, agent configuration, files, and team management</summary>

**Agent workspace**: Follow answers, tool activity, cooperating tasks, and file delivery.

> Screenshot placeholder: Agent workspace

**Knowledge bases**: Manage document processing, retrieval tests, and evaluation.

> Screenshot placeholder: Knowledge bases

**Knowledge graphs**: Build entities and relationships, then explore related subgraphs.

> Screenshot placeholder: Knowledge graphs

**Agent configuration**: Select models, prompts, tools, MCP, and Skills.

> Screenshot placeholder: Agent configuration

**Workspace files**: Preview supported HTML, PDF, Markdown, images, and code, and download artifacts.

> Screenshot placeholder: Workspace files

**Team management**: Manage users, departments, and shared resource scopes.

> Screenshot placeholder: User and department management

</details>

## Contributing

Issues, documentation improvements, bug fixes, and new features are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and the [contribution guide](docs/develop-guides/contributing.md) for the full guidelines.

Thanks to all contributors for supporting this project!

<a href="https://github.com/xerrors/Yuxi/contributors">
  <img src="https://contrib.rocks/image?repo=xerrors/Yuxi&max=100&columns=10" />
</a>

---

Yuxi's implementation and documentation draw on the following excellent open-source projects:

- [LightRAG](https://github.com/HKUDS/LightRAG): Early graph construction and retrieval ideas.
- [DeepAgents](https://github.com/langchain-ai/deepagents): Deep agent framework.
- [DeerFlow](https://github.com/bytedance/deer-flow): Sandbox agent architecture ideas.
- [RAGFlow](https://github.com/infiniflow/ragflow): Document chunking strategies.
- [LangGraph](https://github.com/langchain-ai/langgraph): Agent orchestration foundation.
- [QwenPaw](https://github.com/agentscope-ai/QwenPaw): Model configuration and personal file area design.

## License

Yuxi itself is licensed under the MIT License. See [LICENSE](LICENSE) for details. Third-party components included through Docker Compose retain their own licenses. Before redistribution or commercial deployment, check the upstream licenses and source-code obligations for the actual image versions you use; see the [production deployment guide](docs/advanced/deployment.md) for the relevant boundaries.

[![Give Yuxi a Star](https://xerrors.oss-cn-shanghai.aliyuncs.com/posts/2026/08/20260818-184409-image-da91658b.png)](https://github.com/xerrors/Yuxi)
