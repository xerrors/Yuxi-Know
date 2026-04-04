# 开发路线图

路线图可能会经常变更，如果有强烈的建议，可以在 [issue](https://github.com/xerrors/Yuxi/issues) 中提。

日志添加规范（For Agent）:

- 同一版本的多次功能更新时，应以功能为单位进行更新，比如之前添加了 A 功能的更新，在后续的更新中修复了因 A 功能引入的 bug，那么这个修复说明应该和 A 功能描述放在一起，而不是新增一条修复记录，功能更新同理。


### 看板

- Langfuse 增加 self-host 模式支持，补齐私有化部署与配置说明（已支持 cloud，待调试）
- 检索测试中，添加问答
- 集成 Memory，基于 deepagents 的文件后端实现，需要考虑定位
- 添加自定义向量模型和 rerank 模型的配置，在网页上面 `0.7`
- Yuxi-cli 相关的功能，放在后续版本中实现（不是类似于编程助手，而是管理平台的工，等各个 router 接口优化之后）
- 完善个人知识库（仅设想，欢迎讨论）

### Bugs
- 目前的知识库的图片存在公开访问风险
- 生成基准测试会把所有的向量都计算一遍不合理

### BREAKING CHANGE（不兼容变更，0.7 版本再实现）
- 将自定义provider 的实现逻辑，从文件移动到数据库中，并将相关处理代码，移出 config 文件，放到 provider 模块中
- 优化知识库的 API 接口设计，使用 /{db_id}/xxx 的形式，整合 mindmap / eval 接口



## 版本记录

### 0.6.1

<!-- 0.6.1 的内容请放在这里 -->
- 调整 backend Python 工作区依赖边界：将 `backend/package/yuxi` 明确为承载核心运行依赖的业务包，根 `backend/pyproject.toml` 仅保留工作区入口与开发/测试配置，减少依赖职责混淆。
- 将 `yuxi` 从 uv workspace 成员调整为 `backend/package` 下可独立构建的本地 Python 包，backend 通过 path dependency 以已安装包形式发现依赖，移除对 `PYTHONPATH=/app/package` 的运行时耦合。
- 修复沙盒 `workspace` 隔离粒度：宿主机目录从共享 `saves/threads/shared/workspace` 收敛为用户级 `saves/threads/shared/<user_id>/workspace`，并同步传递 `user_id` 到 sandbox 路径解析、provisioner 挂载与 viewer/chat 测试，保证同用户跨线程共享、不同用户隔离。
- 调整输入框 `@` 提及中的文件搜索交互：无查询内容时不再直接展示文件列表，改为提示“输入相关内容以搜索文件”，避免未过滤结果干扰选择。
- 收紧文件系统安全边界：viewer/chat 下载与删除路径统一基于解析后的真实路径做允许目录校验，阻止通过软链接逃逸工作区/线程目录；同时将密码哈希默认实现升级为 Argon2，并移除 skill frontmatter 解析中的正则回溯风险。
- 调整 Skills 导入能力：`/api/system/skills/import` 现在除 ZIP 外也支持直接上传单个 `SKILL.md`，前端上传入口与后端导入服务同步兼容，便于快速导入单文件技能
- 新增 Skills 远程安装能力：Skills 管理页支持填写 `owner/repo` 或 GitHub URL，后端通过隔离的临时 `HOME` 调用 `npx skills add` 下载指定 skill，再复用现有导入链路写入 `saves/skills` 和数据库，避免将 `~/.agents/skills` 直接作为系统主存储；前端远程安装弹窗补充多选串行安装与批量进度展示，复用现有单 skill 安装接口逐个提交请求
- 调整部门删除语义：删除部门时不再要求用户数为 0，而是将部门下用户迁移到默认部门，同时清理部门级配置和部门 API Key，保证测试部门、撤换部门等场景可直接删除，并补充对应集成测试覆盖该链路
- 重构 MCP 运行时配置加载模型：移除 `MCP_SERVERS` 作为运行正确性前提的设计，改为每次直接从数据库读取最新 MCP 配置，并用 `server_name:config_hash` 作为本地工具缓存 key；同时将内置 MCP 初始化职责收敛为仅同步数据库默认项，前端 MCP 选项改为直接使用实时资源列表，解决 `api`/`worker` 分进程下的配置不一致与缓存失效问题

---

历史版本发布记录已迁移到 [版本变更记录](./changelog.md)。

维护说明：
- roadmap 仅保留未来规划（看板/Bugs/里程碑方向）。
- 具体版本发布内容统一维护在 changelog。
