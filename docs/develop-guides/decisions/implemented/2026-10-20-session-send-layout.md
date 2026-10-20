# 新建会话发送布局连续性

状态：implemented
类型：bug-fix
Owner：frontend/src/app/layouts/sessionRouteCache.ts

## 问题

新建页发送首条输入后，正式路由创建另一份会话视图，重复读取智能体与历史。加载期间编辑器被替换成高度不同的提示，回执到正式消息消费之间用户消息暂时消失。多行编辑器移到底部后又因清空文本延迟调整高度，产生二次收缩。智能体和消息加载使用两个底部提示，其中消息提示使用自制 spinner。首条输入的气泡、排队行、回复等待和页面加载还会在同一帧重复展示。

## 决策

### 实现方案

[路由缓存身份](https://github.com/xerrors/Yuxi/blob/main/frontend/src/app/layouts/sessionRouteCache.ts)把当前新建页交接给刚创建的正式会话，实际成功导航的 `afterEach` 登记该身份并分配下一张新建页。原导航被同目标后继导航取消时，交接仍由后继成功导航完成；成功离开到其他页面丢弃待交接。AppLayout 卸载时注销导航观察。其他会话继续独立保活，草稿、侧栏、模型选择和滚动状态由各自视图拥有。该决定补充[会话协作的视图隔离](2026-10-03-session-cooperation.md)。

[SessionWorkspace](https://github.com/xerrors/Yuxi/blob/main/frontend/src/modules/session/ui/SessionWorkspace.vue)在首条发送冻结载荷后清空文本，并同时结束欢迎布局、移除项目选择、保留底部说明空间。创建失败恢复冻结文本与图片，后来编辑的文本保留。编辑器空值在下一个 DOM 更新时立即同步高度，非空输入保留防抖。智能体校验期间保留编辑器并禁用输入；错误与不可用状态保留可观察提示。请求正在提交时不显示“结果待确认”的重试入口。

`sessionInput` 把已接收但尚未消费的首条输入保留为带 `queued` 状态的乐观展示，消费快照到达后接管；不写入正式 item。工作区把已有气泡的当前主输入从底部队列展示列表去重，在 Run 尚未启动时，回复位置保留绑定该 Input 的取消操作；Run 启动后使用既有停止入口。原始队列与计数保持完整，暂停、附件准备和后续输入仍保留原队列入口。持久 Input、权限、队列与 SSE 协议沿用原有 Owner。

首次创建与未完成历史加载由内容区约 30% 高度的单个 `a-spin` 展示；已加载会话重新校验智能体时保留内容，不恢复页面加载。页面加载与回复等待提示互斥。回复位置保留独立的星形流式指示器、文字呼吸动画和“正在生成回复”文案，仅取消会移动整个提示的挂载位移动画。页面加载使用应用入口注册的统一指示器，不占据编辑器布局。

## 替代方案

- 全部会话共享一个页面：会破坏独立侧栏、滚动与编辑状态。
- 只添加 CSS 动画：页面重建、消息闪退和编辑器卸载仍然存在。
- 正式页等待完整加载后替换新建页：增加额外页面交接和等待协调。
- 保留两个加载提示：重复表达同一个等待过程，并继续影响编辑器附近布局。

## 后果

首条发送从欢迎布局移到底部一次，后续回执、消费、首 token 与正文增长保持编辑器的几何位置。缓存身份在布局实例内分配，不写入 URL 或持久业务数据。创建失败会恢复草稿；运行中后续输入仍遵循 FIFO。加载提示、生成提示和持久终态分别表达各自事实。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 正式路由保持原视图，其他会话独立 | key 变化、竞争导航撤销身份或不同会话串状态 | AppLayout、AgentView、sessionRouteCache | 六项真实 memory router unit；浏览器返回同一编辑器、草稿隔离与刷新恢复 | 旧 `route.path` 装配被同一浏览器探针检出编辑器替换；覆盖同目标导航两种完成顺序、取消、异常、重定向与迟到事件 | Passed |
| 加载统一、互斥且不挤压编辑器，不可用时禁止发送 | 同帧重复 spinner、卸载编辑器或校验期间可发送 | SessionWorkspace、应用 Spin 注册 | 模板状态矩阵；延迟真实响应的浏览器检查仅一个统一指示器，指示器顶部位于视口高度的 40% 以内；503 时编辑器保留且禁用 | ready/loading/error/unavailable、多个同时加载、已加载后重新校验、未知结果与提交中分别断言 | Passed |
| 普通和多行首条消息到真实流式输出不闪退、不重复，底部稳定 | 回执间隙或延迟清空使消息消失、编辑器二次收缩 | SessionWorkspace、sessionInput、MessageInputComponent | 浏览器执行 [sessionSendLayout.js](https://github.com/xerrors/Yuxi/blob/main/frontend/test/browser/sessionSendLayout.js)，真实 HTTP、worker、模型与 SSE；回读 result_run_id 对应最终输出 | 同一探针运行旧代码检出四次底部几何状态与消息闪退；多行修复前检出 177px 到 108px 二次收缩 | Passed |

实际执行 `docker compose exec -T frontend pnpm run lint:check`、`docker compose exec -T frontend pnpm run test:unit`（740 passed）、`docker compose exec -T frontend pnpm run build` 均通过；build 保留既有大 chunk 提示。普通、延迟真实 HTTP 响应和多行探针分别观察到 27、72 和 53 次正文增长，均为 completed，用户消息和最终回答各一条，落底后位置和尺寸只有一个取值。逐帧检查还拒绝消息与底部队列重复、同帧页面和回复 Loading 并存、已有消息后恢复页面 Loading、首条输入短暂显示排队中间态；同一探针在上一候选实现检测到四项违规，当前三个样本均零违规。延迟响应样本只延长真实响应时间，不替换服务数据。768、1024、2048px 无页面横向溢出，768px 浅色、暗色、加载及错误状态已检查。

`python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`（66 passed）、`docker compose exec -T api uv run --group test pytest test/unit -m "not slow"`（2921 passed、99 skipped）与 `pnpm --dir docs run build` 已通过。后端 skip 不计为通过。独立 Reviewer 复审相关 45 项测试通过。

真实流式探针使用专用无 MCP 的测试智能体和现有模型；原账号的 MCP 授权受本地加密配置错误影响，此能力未验证，也未修改其配置。模型首 token 延迟随 provider 变化，前后样本不用于声称模型响应提速。
