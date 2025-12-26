---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "Yuxi-Know"
  text: "智能知识库与知识图谱问答系统"
  tagline: 基于 LangGraph + Vue.js + FastAPI + LightRAG 架构构建的智能问答平台
  image:
    src: /bb.png
    alt: VitePress
  actions:
    - theme: brand
      text: Latest 文档
      link: /latest/intro/quick-start
    - theme: alt
      text: v0.4.0 文档
      link: /v0.4.0/intro/quick-start

features:
  - title: 🤖 智能体与模型
    details: 支持主流大模型及 vLLM、Ollama 等，支持自定义智能体开发，兼容 LangGraph 部署
  - title: 📚 灵活知识库
    details: 支持 LightRAG、Milvus、Chroma 等存储形式，配置 MinerU、PP-Structure-V3 文档解析引擎
  - title: 🕸️ 知识图谱
    details: 支持 LightRAG 自动图谱构建，以及自定义图谱问答，可接入现有知识图谱
  - title: 👥 权限安全
    details: 支持超级管理员、管理员、普通用户三级权限体系，并配置内容审查以及守卫模型
  - title: 🔧 易于部署
    details: 基于 Docker Compose 一键部署，支持热重载开发，无需显卡即可运行
  - title: 🎯 生产就绪
    details: 完整的测试套件、API 文档、监控日志，适合企业级部署和使用
---

## 快速开始

```sh
docker compose up --build -d
```

## 在线演示

观看视频演示：[Bilibili](https://www.bilibili.com/video/BV1DF14BTETq)
