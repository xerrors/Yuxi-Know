# 开发路线图

路线图可能会经常变更，如果有强烈的建议，可以在 [issue](https://github.com/xerrors/Yuxi/issues) 中提。

项目看板（Maintainer Only）：[GitHub Project](https://github.com/users/xerrors/projects/2)


后续 0.8 的非兼容计划更新

1. Milvus 3.0 https://milvus.io/docs/zh/release_notes.md
2. API 和 Worker 等从文件系统解耦，分布式部署


### 看板

**知识库**
- [ ] 知识库 Mindmap 扩展：新增基于文件名的文件“边”构建，支持聚类算法形成社区节点，并提供思维导图 (Mindmap) 可视化结构展示
- [ ] 知识库工具新增 query_keywords 工具，专门用于基于关键词命中的排序 
- [ ] 增强知识库检索体验：增强 metadata、标签等
- [ ] 个人工作区增加可检索能力（但是不做向量化）

**智能体**
- [ ] 子智能体缺少 steer 机制 
- [ ] 子智能体的双向通信，缺少 ask_for_main_agent 的机制
- [ ] 子智能体与子智能体的通信机制

**其他**
- [ ] 集成 Memory，基于 deepagents 的文件后端实现，需要考虑定位
- [ ] 优化 Agent 向用户追问交互：支持较长文本回答输入，并在流式输出时保持聊天区跟随最新内容（[#753](https://github.com/xerrors/Yuxi/issues/753)）


### Bugs
- [ ] 目前的知识库的图片存在公开访问风险
- [ ] 点开对话的时候要能够自动定位到尾部，而不是最开始。

---

历史版本发布记录已迁移到 [版本变更记录](./changelog.md)。

维护说明：
- roadmap 仅保留未来规划（看板/Bugs/里程碑方向）。
- 具体版本发布内容统一维护在 changelog。
