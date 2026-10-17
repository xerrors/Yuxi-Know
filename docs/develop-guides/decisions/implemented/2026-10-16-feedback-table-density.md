# 反馈列表使用紧凑工具栏与统一表格行高

状态：implemented
类型：simplification
Owner：frontend/src/modules/dashboard/ui/AgentFeedbackList.vue

## 问题

反馈页重复展示标题、说明和排序文案，筛选与刷新分散，占用首屏空间。列表用网格卡片模拟表格，正文保留换行且行高随内容变化，难以连续扫描记录。

## 决策

### 实现方案

删除重复标题、副标题、导航中的重复说明和独立加载数量栏。反馈来源使用下拉选择，包含全部来源、用户评价和智能体标记，智能体筛选、条件评价筛选、数量、重置与刷新放入同一工具栏，按容器宽度自然换行。

列表使用语义 HTML table，列宽与表头统一；每条记录采用相同 64px 行高，反馈摘要折叠空白并最多两行，完整正文通过现有详情查看。窄容器保留普通表格并横向滚动，不再转为卡片。沿用当前筛选、分页、重试、焦点恢复和 Langfuse 入口，后端接口与数据保持不变。

## 替代方案

- 保留卡片网格并仅减小留白：仍有响应式变形和内容驱动行高，不符合普通表格要求。
- 单行省略全部摘要：更密集，但减少直接可读的信息；两行摘要在固定行高内兼顾阅读量。
- 根据内容自然撑高：破坏记录对齐和扫描节奏。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 筛选与刷新在紧凑工具栏，来源为下拉选择 | 重复说明或分段滑块残留 | AgentFeedbackList | 真实浏览器 DOM、截图、前端 lint/build | 恢复旧标题、单选来源或 segmented，断言失败 | Passed |
| 长、短、空说明和多段文本的行高一致 | 正文换行或内容撑高 | AgentFeedbackList | 浏览器读取每行尺寸、详情完整正文 | 混合长度与空白段落，恢复旧布局会失去 table 或统一行高 | Passed |
| 来源/Agent/评价筛选、分页、空错状态与详情可用 | 视觉修改破坏既有操作 | AgentFeedbackList、feedbackApi | 相关 unit、固定协议 fixture 的真实页面交互 | 后页失败保留记录、重试游标、无记录空状态 | Passed |

旧能力不存在：重复的反馈记录标题、副标题、独立加载数量栏、分段滑块及窄屏卡片布局不再出现。

重新引入条件：只有明确的新增用户任务需要独立说明或卡片交互时，重新评估其首屏成本。

## 后果

摘要隐藏两行之外的文本，详情必须保留完整正文。768px 及以上的窄容器可能需要横向滚动，列与操作不能被裁切。当前其他任务对 Langfuse 导航的修改属于已有行为，改版需保持其逻辑与测试。

浏览器运行 `playwright-cli -s=feedback-table --raw run-code --filename=frontend/test/browser/feedbackTable.js`，固定协议 fixture 覆盖浅深色、768/1024/1440/1920px、12 条混合长短/空/多段反馈、统一行高、详情完整正文与关闭后焦点恢复、三类筛选、重置、后页失败沿用游标重试、空状态和错误重试。改前脚本因重复标题残留失败；中间不合理的操作列换行也由行高断言拒绝。1440px、1000px 高的验证窗口首屏可见全部 12 条记录。

`docker compose exec frontend sh -c 'node --test test/unit/sessionFeedback.test.js test/unit/turnTraceNavigation.test.js test/unit/guiFeedback.test.js'` 为 21 项通过。前端 lint 与 build 通过。无后端、权限、持久化或反馈写入变更；浏览器 fixture 不替代真实鉴权和数据库证据。已有 `agentFeedback.js` 的 UI 选择器同步改为来源下拉与工具栏，其依赖真实会话的完整写入流程未执行；原会话跳转相关步骤属于之前的 Langfuse 导航变更，不在本次布局验证范围。

全量前端单测 `docker compose exec frontend pnpm run test:unit` 为 644 passed、1 failed；失败仍是本次未修改、此前已出现的 `markdown_preview_fallback.test.js` 原型宏污染用例。工程契约检查、66 项 verifier 单测与文档构建通过。独立 Reviewer 复跑固定协议浏览器验收与相关 21 项 unit 通过，确认组件 script 与改版前完全相同。
