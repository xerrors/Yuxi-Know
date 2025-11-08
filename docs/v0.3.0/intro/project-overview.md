# 项目简介

Yuxi-Know（语析）是一个基于知识图谱和向量数据库的智能知识库系统，融合了 RAG（检索增强生成）技术与知识图谱技术，为用户提供智能问答和知识管理服务。

特点是技术栈简单，易于上手，使用 MIT 开源协议，非常适合二次开发使用。

### 技术栈选择

- **后端服务**: [FastAPI](https://github.com/tiangolo/fastapi) + Python 3.12+
- **前端界面**: [Vue.js 3](https://github.com/vuejs/vue) + [Ant Design Vue](https://github.com/vueComponent/ant-design-vue)
- **数据库存储**: [SQLite](https://github.com/sqlite/sqlite) + [MinIO](https://github.com/minio/minio)
- **知识存储**: [Milvus](https://github.com/milvus-io/milvus)、[Chroma](https://github.com/chroma-core/chroma)（向量数据库）+ [Neo4j](https://github.com/neo4j/neo4j)（图数据库）
- **智能体框架**: [LangGraph](https://github.com/langchain-ai/langgraph)
- **文档解析**: [LightRAG](https://github.com/HKUDS/LightRAG) + [MinerU](https://github.com/HKUDS/MinerU) + [PP-Structure-V3](https://github.com/PaddlePaddle/PaddleOCR)
- **容器编排**: [Docker Compose](https://github.com/docker/compose)

### 核心功能

- **智能问答**: 支持多种大语言模型，提供智能对话和问答服务
- **知识库管理**: 支持多种存储形式（Chroma、Milvus、LightRAG）
- **知识图谱**: 自动构建和可视化知识图谱，支持图查询
- **文档解析**: 支持 PDF、Word、图片等多种格式的智能解析
- **权限管理**: 三级权限体系（超级管理员、管理员、普通用户）
- **内容安全**: 内置内容审查机制，保障服务合规性

## 演示视频

<div align="center">
  <a href="https://www.bilibili.com/video/BV1DF14BTETq" target="_blank">
    <img width="3651" height="1933" alt="视频演示缩略图" src="https://github.com/user-attachments/assets/eac4fa89-2176-46ae-a649-45a125cb6ed1" />
  </a>
  <p style="margin-top: 12px;">
    <a href="https://www.bilibili.com/video/BV1DF14BTETq" target="_blank" style="text-decoration: none; color: #23ade5; font-weight: 500;">
      📽️ 点击查看视频演示 <i class="fa fa-external-link" style="margin-left: 4px;"></i>
    </a>
  </p>
</div>