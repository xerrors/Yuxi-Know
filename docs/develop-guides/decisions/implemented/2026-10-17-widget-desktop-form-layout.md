# 对话表单的桌面宽度与字段排布

状态：implemented
类型：bug-fix
Owner：frontend/src/shared/ui/WidgetRenderer.vue

## 问题

普通桌面对话正文宽 736px，默认表单卡片仅 440px。五项输入单列排列时卡片高约 618px，用户需要滚动才能查看提交操作，正文重复说明进一步占用空间。

## 决策

### 实现方案

WidgetRenderer 的样式让包含 Form 的默认 md 卡片使用所在正文宽度，保留显式 sm、lg 尺寸和非表单卡片。Form 使用随实际可用宽度排布的网格；当前桌面正文可容纳两列短字段，多行文本、三项以上单选、说明和现有 Row/Col 容器占整行，提交操作右对齐。WidgetNode 给多行字段添加呈现类。沿用现有颜色、原生表单、校验与提交链路，不新增协议字段或依赖。

chat-widgets 的表单示例使用 full 卡片与紧凑标题，说明集中在填写所需条件，必填由字段标记表达。历史消息由渲染器直接改善，新消息通过既有 Skill 按需读取获得相同引导。本变更不调整 ask_user_question 与 Form 的选择机制，不实现流式呈现。

## 替代方案

- 只让模型使用 size:full：旧消息继续保持窄单列表单，无法覆盖现有消费者。
- 所有卡片统一加宽：影响图片、摘要等无关内容的已有尺寸语义。
- 增加列数、跨列等新协议：当前字段类型足以确定基础排布，不增加模型输出负担。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 历史表单在正常桌面正文中利用横向空间 | 实际 DOM 与样式 | WidgetRenderer/WidgetNode | 1440×1000 和 1920×1080 真实完整页面、宽高与字段坐标 | 同一历史卡片旧布局实测 440px 单列、高约 618px | Passed |
| 多行备注整行、提交可见、填写顺序与结果一致 | 原生 Form、网格布局 | WidgetNode/sessionInput | 浏览器填写、提交、刷新后消息与模型结果；现有专项 unit | 空表单点击提交未发消息；两列字段逐项对应，日期保持 YYYY-MM-DD | Passed |
| 新 Skill 在真实任务中生效 | 按需发现、模型输出 | chat-widgets/SKILL.md | 工具详情含 2026.10.17.1 及紧凑引导，最终 DOM 为 full Card、md 标题、两行备注 | 未读取新版不计新引导通过，旧提问工具不计 Form 通过 | Passed |

浏览器使用真实 Yuxi 页面提问、填写、提交及刷新，没有手工调用业务 API、替换模型响应或注入历史。相同历史卡片由 440×618px 变为 736×446px；新任务“给一张一次填写的工作坊通知表单，提交后生成150字以内邀请通知”生成 736×420px 卡片，短字段各 333px、备注 686px，提交按钮位于视口底边以内。1440×1000 与 1920×1080 均为两列、无横向溢出。显式 lg 的出游表单仍宽 560px，三项单选整行排列。明暗主题完整页面截图与会话保留在本地，不提交运行产物。

工作坊表单填写文本、2026-11-14 日期及线下选项后提交，普通用户消息逐项保留五项内容；模型通知包含主题、日期、形式、参加对象、时间、地点和携带要求，正文去空白后独立计数为101字。刷新后用户消息与通知仍在。布局不改变 Form 的原生校验和现有消息发送语义。

| 命令 | 结果 |
|---|---|
| `docker compose exec -T frontend node --test test/unit/widgetSubmission.test.js test/unit/widgetForms.test.js` | Passed，31 tests |
| `docker compose exec -T frontend pnpm run test:unit` | Passed，692 tests |
| `docker compose exec -T frontend pnpm run lint:check` | Passed |
| `docker compose exec -T frontend pnpm run build` | Passed，含 typecheck |
| `docker compose exec -T api uv run --group test pytest test/unit -m "not slow"` | 2720 passed、62 skipped、7 subtests passed；跳过项不计能力通过 |
| Skill 围栏逐个调用 `parseWidget` | Passed，5 examples |
| `python3 scripts/verify_engineering_contracts.py` | Passed，217 decisions |
| `python3 -m unittest scripts.test_verify_engineering_contracts` | Passed，66 tests |
| docs：`pnpm run build` | Passed，包含相对链接检查 |
| `git diff --check` | Passed |

## 后果

两列只用于可用宽度足够的表单，显式容器仍承载模型要求的分组。模型额外生成的正文不由前端删除；新 Skill 的简洁引导仅通过真实样本验证。本次按用户要求只做正常桌面宽度的视觉验收。

构建保留现有 bundle 大小提示，后端保留依赖弃用及 pytest 缓存目录权限警告。开发浏览器有现有语法高亮模块加载警告；本次表单交互及最终持久消息可正常回读，该独立问题未修复。
