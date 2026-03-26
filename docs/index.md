---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "Yuxi"
  text: "智能知识库与知识图谱智能体开发平台"
  tagline: 基于 LangGraph v1 + Vue.js + FastAPI + LightRAG，统一构建 RAG、知识图谱与多智能体应用
  image:
    src: /bb.png
    alt: Yuxi
  actions:
    - theme: brand
      text: 快速开始
      link: /intro/quick-start
    - theme: alt
      text: 智能体开发
      link: /agents/agents-config
    - theme: alt
      text: GitHub
      link: https://github.com/xerrors/Yuxi

features:
  - title: 🤖 智能体开发
    details: 基于 LangGraph v1，支持 Agents、SubAgents、Tools、MCP、Skills 与中间件配置，适合搭建真实业务智能体
  - title: 📚 知识库与 RAG
    details: 支持多格式文档上传、解析、分块、向量检索与评估，兼容结构化与非结构化知识管理场景
  - title: 🕸️ 知识图谱
    details: 基于 LightRAG 构建图谱问答与图谱检索，支持自动图谱生成、属性图谱导入与可视化分析
---

## 项目定位

Yuxi（语析）不是单一的问答页面，而是一个面向开发者与团队的 AI 应用平台。它把知识库、知识图谱和智能体开发放在同一套系统里，适合从原型验证一路走到团队内部落地。

你可以用它完成这些事情：

- 构建面向业务场景的 RAG + 知识图谱智能体
- 将 PDF、Word、Markdown、图片等资料转为可检索、可推理的知识资产
- 基于 LangGraph v1 搭建多智能体、子智能体和工具调用流程
- 为内部系统提供可管理、可扩展的 AI 能力底座

## 文档入口

- [快速开始](/intro/quick-start)：完成环境初始化、容器启动与首次登录
- [项目简介](/intro/project-overview)：了解整体定位、技术栈与核心能力
- [知识库与知识图谱](/intro/knowledge-base)：查看知识导入、检索与图谱能力
- [智能体开发](/agents/agents-config)：配置 Agent、Tools、MCP、Skills 与中间件
- [生产部署](/advanced/deployment)：了解部署方式与上线建议


自动生成文档镜像：

- [Zread](https://zread.ai/xerrors/Yuxi)
- [DeepWiki](https://deepwiki.com/xerrors/Yuxi)
