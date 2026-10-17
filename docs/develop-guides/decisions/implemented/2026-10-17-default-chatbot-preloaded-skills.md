# 智能助手预加载对话组件与知识库技能

状态：implemented
类型：feature
Owner：backend/yuxi/modules/agents/presets/default_chatbot.py

## 问题

智能助手需要从首轮获得对话组件和知识库技能的完整说明，减少按需发现的不确定性。

## 决策

### 实现方案

默认助手预设的 context.preload_skills 使用内置标识 chat-widgets 与 knowledge-base。Skills 可用范围沿用 Chatbot 的默认全部；运行准备继续按访问权限解析预加载与依赖工具。预设初始化仅为新记录写入默认配置，已持久化配置保留用户选择。

默认助手的选择部分取代[对话组件决定](2026-10-12-chat-widgets.md)中的按需加载默认；通用 Chatbot 的空预加载默认值继续保留。

## 替代方案

按需读取保留发现成本；预加载全部会扩大无关提示和工具范围。固定预加载这两个 Skill 对应用户明确选择。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 默认助手预加载有效内置技能，保留授权与默认选择语义 | 预设发现、资源归一化与指令注入 | default_chatbot / context / SkillsMiddleware | 实际发现预设并构造 ChatBotContext，两个 slug 与内置文件头匹配，skills 保持 all；既有发现、context、runtime 与 middleware 85 项单测通过 | 不可访问技能被过滤，预加载说明不重复注入，其他 Skill 保持按需加载 | Passed |

执行 `docker compose exec -T api uv run --group test pytest test/unit/agents/test_builtin_discovery.py test/unit/agents/test_context_auth.py test/unit/agents/skills/test_skill_runtime.py test/unit/middlewares/test_skills_middleware.py -q`，85 passed。Ruff 的格式与 lint 检查通过。

`docker compose exec -T api uv run --group test pytest test/unit/repositories/test_agent_repository.py -q`，60 passed。默认助手创建用例以两个明确标识校验新记录的 config_json，删除预设配置或写错技能名会失败。

## 后果

预加载增加首轮提示长度并提前开放授权依赖工具。已有部署需要通过助手配置选择这两个预加载项，重启不会覆盖已有配置。
