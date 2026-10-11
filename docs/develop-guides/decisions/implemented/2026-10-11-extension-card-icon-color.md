# 扩展卡片图标颜色

状态：implemented
类型：feature
Owner：frontend/src/shared/ui/InfoCard.vue

## 问题

工具和技能卡片使用同一灰色图标底板，图标之间不易快速区分。颜色需要随扩展身份保持稳定，同时适配浅色和深色主题。

## 决策

`InfoCard` 的图标底板默认无边框，所有使用该组件的卡片都遵循此默认；调用方可通过 `iconBorder` 显式开启边框。可选 `iconColor` 控制图标前景色和淡色底板。工具列表根据工具 ID、技能列表根据 Skill ID（无 ID 时使用 slug）、推荐技能套件根据套件 ID，对 avatar 的 `studio` 预设颜色取模；浅深主题使用同一索引的对应色值，卡片主体背景和文字继续由现有主题 token 控制。

### 实现方案

`ToolsCardList.vue` 与 `SkillCardList.vue` 各自把工具 ID、Skill ID（无 ID 时使用 slug） 或套件 ID 交给 `extensionIconColor.js` 的稳定哈希函数，并读取当前主题；工具与普通 Skill 卡片通过 `iconColor` 传给共享 `InfoCard.vue`，套件卡片由 `SkillSuiteCard.vue` 应用同一色彩规则。`InfoCard.vue` 对所有调用方统一提供无边框图标底板与可选 `iconBorder` 属性。卡片组件只消费颜色和边框属性并绘制图标底板，不知道扩展身份或色卡定义。没有身份的卡片不传入颜色属性，沿用中性样式。

## 替代方案

- 在工具和技能列表页内分别设置图标和底板样式：颜色逻辑会绕过卡片组件，难以保证列表之间一致。
- 只按列表顺序循环颜色：筛选、排序或刷新后同一工具会变色。
- 给全部信息卡统一着色：会改变知识库、MCP 和设置卡片的既有层级。

## 后果

扩展颜色由工具 ID、Skill ID（无 ID 时使用 slug） 或套件 ID 决定，主题切换不改变颜色类别；新增扩展只需有身份即可映射。颜色属于装饰性识别，不承载分类或状态语义。所有 `InfoCard` 调用方的图标边框默认关闭，需要边框时显式设置 `iconBorder`。

## 验证

- `docker compose exec frontend pnpm run lint:check`：通过。
- `docker compose exec frontend pnpm run build`：通过；保留仓库现有 CSS minify 与 chunk size 警告。
- `docker compose exec -T frontend pnpm run test:unit`：559 passed，0 failed；`pnpm run lint:check`、`pnpm run build`：通过。
- 5173 工具和技能列表：真实卡片显示多色图标及浅色底板；浅色与深色主题均检查通过，同一扩展身份的颜色映射保持稳定。
- `cd docs && pnpm run build`：通过，保留完整相对链接检查；修正测试审计文档中的两处根目录 AGENTS 链接为公开源码链接。
- `git diff --check`：通过。
