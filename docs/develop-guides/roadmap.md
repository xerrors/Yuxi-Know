# 开发路线图

路线图可能会经常变更，如果有强烈的建议，可以在 [issue](https://github.com/xerrors/Yuxi/issues) 中提。

日志添加规范（For Agent）:

- 同一版本的多次功能更新时，应以功能为单位进行更新，比如之前添加了 A 功能的分不分续保，在后续的更新中修复了因 A 功能引入的 bug，那么这个修复说明应该和 A 功能描述放在一起，而不是新增一条修复记录，功能更新同理。


### 看板

- Langfuse 增加 self-host 模式支持，补齐私有化部署与配置说明
- 检索测试中，添加问答
- 集成 Memory，基于 deepagents 的文件后端实现
- 添加自定义向量模型和 rerank 模型的配置，在网页上面
- Yuxi-cli 相关的功能，放在后续版本中实现（不是类似于编程助手，而是工具）

### Bugs
- 部分异常状态下，智能体的模型名称出现重叠[#279](https://github.com/xerrors/Yuxi/issues/279)
- 部分 local 的 mcp server 无法正常加载，但是建议在项目外部启动 mcp 服务器，然后通过 sse 的方式使用。【未复现】
- 目前的知识库的图片存在公开访问风险
- 生成基准测试会把所有的向量都计算一遍不合理



## 版本记录

### 0.6.1

<!-- 0.6.1 的内容请放在这里 -->
- 调整 backend Python 工作区依赖边界：将 `backend/package/yuxi` 明确为承载核心运行依赖的业务包，根 `backend/pyproject.toml` 仅保留工作区入口与开发/测试配置，减少依赖职责混淆。
- 修复沙盒 `workspace` 隔离粒度：宿主机目录从共享 `saves/threads/shared/workspace` 收敛为用户级 `saves/threads/shared/<user_id>/workspace`，并同步传递 `user_id` 到 sandbox 路径解析、provisioner 挂载与 viewer/chat 测试，保证同用户跨线程共享、不同用户隔离。
- 调整输入框 `@` 提及中的文件搜索交互：无查询内容时不再直接展示文件列表，改为提示“输入相关内容以搜索文件”，避免未过滤结果干扰选择。
- 收紧文件系统安全边界：viewer/chat 下载与删除路径统一基于解析后的真实路径做允许目录校验，阻止通过软链接逃逸工作区/线程目录；同时将密码哈希默认实现升级为 Argon2，并移除 skill frontmatter 解析中的正则回溯风险。
- 调整 Skills 导入能力：`/api/system/skills/import` 现在除 ZIP 外也支持直接上传单个 `SKILL.md`，前端上传入口与后端导入服务同步兼容，便于快速导入单文件技能
- 新增 Skills 远程安装能力：Skills 管理页支持填写 `owner/repo` 或 GitHub URL，后端通过隔离的临时 `HOME` 调用 `npx skills add` 下载指定 skill，再复用现有导入链路写入 `saves/skills` 和数据库，避免将 `~/.agents/skills` 直接作为系统主存储；前端远程安装弹窗补充多选串行安装与批量进度展示，复用现有单 skill 安装接口逐个提交请求

---

历史版本发布记录已迁移到 [版本变更记录](./changelog.md)。

维护说明：
- roadmap 仅保留未来规划（看板/Bugs/里程碑方向）。
- 具体版本发布内容统一维护在 changelog。
