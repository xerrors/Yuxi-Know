# 开发路线图

路线图可能会经常变更，如果有强烈的建议，可以在 [issue](https://github.com/xerrors/Yuxi-Know/issues) 中提。

- **[2025/10/13]** v0.3 进入 beta 测试环节，不会再封装新的特性，仅作 bug 层面的修复


## Bugs

- [ ] upload 接口会阻塞主进程
- [ ] LightRAG 知识库查看不了解析后的文本，偶然出现，未复现

## Next

- [ ] 新建 DeepAgents 智能体
- [ ] 添加对于上传文件的支持
- [ ] LightRAG 知识库应该可以支持修改 LLM
- [ ] 统一图谱数据结构，优化可视化方式 [#298](https://github.com/xerrors/Yuxi-Know/issues/298) <Badge type="info" text="0.4" />
- [ ] 集成智能体评估，首先使用命令行来实现，然后考虑放在 UI 里面展示
- [ ] 开发与生产环境隔离，构建生产镜像 <Badge type="info" text="0.4" />


## Later

下面的功能**可能**会放在后续版本实现，暂时未定

- [ ] 集成 LangFuse (观望) 添加用户日志与用户反馈模块，可以在 AgentView 中查看信息

## Done


- [x] 添加测试脚本，覆盖最常见的功能（已覆盖API）
- [x] 新建 tasker 模块，用来管理所有的后台任务，UI 上使用侧边栏管理。
- [x] 优化对文档信息的检索展示（检索结果页、详情页）
- [x] 当前 ReAct 智能体有消息顺序错乱的 bug，且不会默认调用工具
- [x] 优化全局配置的管理模型，优化配置管理
- [x] 支持 MinerU 2.5 的解析方法 <Badge type="info" text="0.3.5" />
- [x] 文件管理：（1）文件选择的时候会跨数据库；（2）文件校验会算上失败的文件；
- [x] Tasker 中获取历史任务的时候，仅获取 top100 个 task。
- [x] 修改现有的智能体Demo，并尽量将默认助手的特性兼容到 LangGraph 的 [`create_agent`](https://docs.langchain.com/oss/python/langchain/agents) 中
- [x] 基于 create_agent 创建 SQL Viewer 智能体 <Badge type="info" text="0.3.5" />
- [x] 优化 MCP 逻辑，支持 common + special 创建方式 <Badge type="info" text="0.3.5" />
- [x] 修复本地知识库的 metadata 和 向量数据库中不一致的情况。
- [x] v1 版本的 LangGraph 的工具渲染有问题