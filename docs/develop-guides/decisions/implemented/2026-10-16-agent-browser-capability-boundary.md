# Agent 浏览器触发与跨会话配置

状态：implemented
类型：feature
Owner：backend/yuxi/modules/agents/runtime/agent_backends/chatbot/prompt.py

## 问题

模型有时没有把“搜索网页事实”和“实际打开并操作网站”区分开；临时浏览器上下文也不会保存跨对话登录状态。截图可能只被写入文件或被描述为已展示，却没有出现在用户实际看到的聊天 DOM 中。

## 决策

### 实现方案

常驻 chatbot 提示词用简短规则路由：网页事实查询走 `web_search`，简单问题最多搜索一次；需要打开、交互、截图或核验指定网站时按需读取已安装的 `agent-browser` 或 `playwright-cli` Skill，未安装时提示从 Skills 推荐安装；稳定常识和本地工作不浏览。浏览器 profile、session、状态复用与操作生命周期由所选 CLI 和官方 Skill 管理。聊天内的截图按 `chat-widgets` Image/ImageGroup 协议展示；`present_artifacts` 留给用户要下载或交付的文件。

前端 `SkillCardList.vue` 在推荐区提供“浏览器与网页自动化”分组，分别引用 Vercel `vercel-labs/agent-browser` 与 Microsoft `microsoft/playwright-cli` 官方仓库，复用现有多来源选择、解析与确认安装流程。Yuxi 不维护内置 browser Skill 或配套脚本；安装 Skill 与安装 CLI 是独立操作，依赖按上游指南放在执行命令的用户 VM。

## 替代方案

- 每次启动临时 context：不能保留 Cookies、Local Storage 或缓存。
- 多个会话同时打开同一 profile：Chromium 不支持同一用户数据目录被并发启动，可能损坏或锁死状态。
- 把整套 Playwright 样例放进主提示词或引入新的浏览器框架/MCP：增加常驻上下文或运行时依赖，当前 VM 的 Playwright 已覆盖需求。
- 自行维护内置 browser Skill：重复维护上游已有的快照、交互、持久会话和依赖安装指南。
- 在主提示词固定 profile 目录、串行策略与登录流程：把特定运行配置强加给所有浏览器任务，并混淆 CLI 原生行为与系统约定。
- 把截图交给 `present_artifacts`：只适合文件下载，不能证明图片进入对话正文。

## 后果

跨对话状态是否复用取决于实际会话配置。agent-browser 在未配置持久化时会在浏览器关闭后丢弃临时状态；持久 profile 或 session 状态恢复需显式启用，详见[上游会话文档](https://agent-browser.dev/sessions)。跨会话基线验证使用 Python Playwright 与 example.com 的合成 localStorage 标记，只证明指定持久目录在同一 VM 内可复用，不代表默认 CLI 行为、真实第三方登录或 VM 重建后的保留。推荐与安装按需进行，不自动给用户安装 CLI 或启动浏览器。

## 验证

- 更新后稳定常识真实对话完成且 0 个工具调用。
- 网页事实真实对话在原提示词下找到了官方文档，但进行了 4 次 `web_search` 和 4 次结果 `grep`。据此把常见单一事实查询改成最多一次搜索；更新提示词后的真实对话只调用 1 次 `web_search`、读取 1 次结果、未调用 Playwright，最终提供官方 Playwright 链接并按一句话作答。
- Python Playwright 基线对话在 example.com 读取标题并截图。截图 `browser_screenshot.png` 经真实 `read_file` 读取；聊天最终消息使用 Image Widget，页面 DOM 中图片 `naturalWidth=1280`、`naturalHeight=823`，无 `present_artifacts` 调用。该证据不覆盖上游 CLI 的操作。
- 对话 A 写入并读回 `yuxi_profile_probe=profile-20261016-A7C9`；重启 API/Worker 后，对话 B 读到同值。数据库回读两次运行均成功，Sandbox `generation=2` 未变化。这里只测了跨对话 profile，不执行真实账号登录。
- 提示词测试检查已安装浏览器 Skill 的选择与未安装提示；内置发现测试确认 shipping Skills 不含自定义 browser。
- 真实 Skills 页面回读确认运行环境不再列出内置 browser；推荐分组可按两个子 Skill 的名称搜索，分别解析正确的官方仓库。固定 HTTP 响应验证双来源确认、空选择禁用、取消选中项不解析及来源 503 错误状态；未执行真实远程安装。浅/深色与 1440、1024、768、375px 下卡片内容没有溢出，已检查推荐区截图。
- 后端相关测试 16 passed；全量 unit 2653 passed、61 skipped；前端 lint、625 项 unit 与 build 通过；工程信任检查的 66 项 unittest 与文档构建通过。
- 用户 VM 模板已有匹配的 Python Playwright、Chromium 与系统库；未增加运行时包。开源方案、依赖和镜像配置比较见 [浏览器方案调研](../../audits/browser-agent-ecosystem-research-2026-10-16.md)。
