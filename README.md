
<div align="center">
<img width="140" height="140" alt="image" src="https://github.com/user-attachments/assets/299137b7-08d8-45b0-9feb-7b4ab35d7b48" />

<h1>语析 - 基于大模型的知识库与知识图谱智能体开发平台</h1>

[![Stable](https://img.shields.io/badge/stable-v0.4.3-blue.svg)](https://github.com/xerrors/Yuxi-Know/tree/v0.4.3)
[![](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=ffffff)](https://github.com/xerrors/Yuxi-Know/blob/main/docker-compose.yml)
[![](https://img.shields.io/github/issues/xerrors/Yuxi-Know?color=F48D73)](https://github.com/xerrors/Yuxi-Know/issues)
[![License](https://img.shields.io/github/license/bitcookies/winrar-keygen.svg?logo=github)](https://github.com/xerrors/Yuxi-Know/blob/main/LICENSE)
[![DeepWiki](https://img.shields.io/badge/DeepWiki-blue.svg)](https://deepwiki.com/xerrors/Yuxi-Know)
[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk5OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTg0IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/xerrors/Yuxi-Know)
[![demo](https://img.shields.io/badge/demo-00A1D6.svg?style=flat&logo=bilibili&logoColor=white)](https://www.bilibili.com/video/BV1DF14BTETq/)


<a href="https://trendshift.io/repositories/15845" target="_blank">
  <img src="https://trendshift.io/api/badge/repositories/15845" alt="Yuxi-Know | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/>
</a>

[**文档中心**](https://xerrors.github.io/Yuxi-Know/) |
[**视频演示**](https://www.bilibili.com/video/BV1DF14BTETq/)

</div>


## 核心特性

- **智能体开发**：基于 LangGraph v1 的多智能体架构，支持子智能体、工具调用与中间件机制
- **知识库（RAG）**：多格式文档上传，支持 Embedding / Rerank 配置及知识库评估
- **知识图谱**：基于 LightRAG 的图谱构建与可视化，支持属性图谱并参与智能体推理
- **平台与工程化**：Vue + FastAPI 架构，支持暗黑模式、Docker 与生产级部署


## 你可以用语析做什么？

- 构建 **面向真实业务的 RAG + 知识图谱智能体**
- 将 PDF / Word / Markdown / 图片快速转化为可推理的知识库
- 自动（LightRAG）或手动构建知识图谱，并用于智能体推理
- 使用 LangGraph v1 构建多智能体 / 子智能体系统

## 最新动态

- **[2025/12/19] v0.4.0 版本发布**
  <details>
  <summary>查看详细更新日志</summary>

  ### 新增
  - 新增对于上传附件的智能体中间件，详见[文档](https://xerrors.github.io/Yuxi-Know/latest/advanced/agents-config.html#%E6%96%87%E4%BB%B6%E4%B8%8A%E4%BC%A0%E4%B8%AD%E9%97%B4%E4%BB%B6)
  - 新增多模态模型支持（当前仅支持图片），详见[文档](https://xerrors.github.io/Yuxi-Know/latest/advanced/agents-config.html#%E5%A4%9A%E6%A8%A1%E6%80%81%E5%9B%BE%E7%89%87%E6%94%AF%E6%8C%81)
  - 新建 DeepAgents 智能体（深度分析智能体），支持 todo，files 等渲染，支持文件的下载。
  - 新增基于知识库文件生成思维导图功能（[#335](https://github.com/xerrors/Yuxi-Know/pull/335#issuecomment-3530976425)）
  - 新增基于知识库文件生成示例问题功能（[#335](https://github.com/xerrors/Yuxi-Know/pull/335#issuecomment-3530976425)）
  - 新增知识库支持文件夹/压缩包上传的功能（[#335](https://github.com/xerrors/Yuxi-Know/pull/335#issuecomment-3530976425)）
  - 新增自定义模型支持、新增 dashscope rerank/embeddings 模型的支持
  - 新增文档解析的图片支持，已支持 MinerU Officical、Docs、Markdown Zip 格式
  - 新增暗色模式支持并调整整体 UI（[#343](https://github.com/xerrors/Yuxi-Know/pull/343)）
  - 新增知识库评估功能，支持导入评估基准或者自动构建评估基准（目前仅支持 Milvus 类型知识库）详见[文档](https://xerrors.github.io/Yuxi-Know/latest/intro/evaluation.html)
  - 新增同名文件处理逻辑：遇到同名文件则在上传区域提示，是否删除旧文件
  - 新增生产环境部署脚本，固定 python 依赖版本，提升部署稳定性
  - 优化图谱可视化方式，统一图谱数据结构，统一使用基于 G6 的可视化方式，同时支持上传带属性的图谱文件，详见[文档](https://xerrors.github.io/Yuxi-Know/latest/intro/knowledge-base.html#_1-%E4%BB%A5%E4%B8%89%E5%85%83%E7%BB%84%E5%BD%A2%E5%BC%8F%E5%AF%BC%E5%85%A5)
  - 优化 DBManager / ConversationManager，支持异步操作
  - 优化 知识库详情页面，更加简洁清晰，增强文件下载功能

  ### 修复
  - 修复重排序模型实际未生效的问题
  - 修复消息中断后消息消失的问题，并改善异常效果
  - 修复当前版本如果调用结果为空的时候，工具调用状态会一直处于调用状态，尽管调用是成功的
  - 修复检索配置实际未生效的问题

  ### 破坏性更新

  - 移除 Chroma 的支持，当前版本标记为移除
  - 移除模型配置预设的 TogetherAI
  </details>

- **[2025/11/05] v0.3.0 版本发布**
  <details>
  <summary>查看详细更新日志</summary>

  - 全面适配 LangChain/LangGraph v1 版本的特性，使用 create_agent 创建智能体入口。
  - 文档解析升级，适配 mineru-2.6 以及 mineru-api。
  - 更多智能体开发套件 中间件、子智能体，更简洁，更易上手。
  </details>


<img width="2592" height="610" alt="image" src="https://github.com/user-attachments/assets/92898cc6-b1f0-4f1d-9491-75297bdfacaa" />



## 快速开始

克隆代码，并初始化

```
git clone --branch v0.4.3 --depth 1 https://github.com/xerrors/Yuxi-Know.git
cd Yuxi-Know

# Linux/macOS
./scripts/init.sh

# Windows PowerShell
.\scripts\init.ps1
```

然后需要使用 docker 启动项目

```
docker compose up --build
```

等待启动完成后，访问 `http://localhost:5173`

## 示例与演示


<img width="4420" height="2510" alt="image" src="https://github.com/user-attachments/assets/76d58c8f-e4ef-4373-8ab6-7c80da568910" />
<br>
<img width="10116" height="5751" alt="11111" src="https://github.com/user-attachments/assets/d3e4fe09-fa48-4686-93ea-2c50300ade21" />
<br>    
<img width="10116" height="5751" alt="22222" src="https://github.com/user-attachments/assets/734a7cce-8b38-48ae-8e21-ca88996e5dde" />

<br>    
<img width="10116" height="5751" alt="1212" src="https://github.com/user-attachments/assets/06d56525-69bf-463a-8360-286b2cf8796f" />
<br>    
<img width="10116" height="5751" alt="44444" src="https://github.com/user-attachments/assets/e390ec4b-8690-4aee-bbb2-3536f7f67dc9" />


## 参与贡献

感谢所有贡献者的支持！

<a href="https://github.com/xerrors/Yuxi-Know/contributors">
  <img src="https://contrib.rocks/image?repo=xerrors/Yuxi-Know&max=100&columns=15" />
</a>


## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=xerrors/Yuxi-Know)](https://star-history.com/#xerrors/Yuxi-Know)

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

---

<div align="center">

**如果这个项目对您有帮助，请不要忘记给我们一个 ⭐️**

[报告问题](https://github.com/xerrors/Yuxi-Know/issues) | [功能请求](https://github.com/xerrors/Yuxi-Know/issues) | [讨论](https://github.com/xerrors/Yuxi-Know/discussions)

</div>
