# 其他前端与开发环境优化

状态：implemented
类型：simplification
Owner：frontend/src/modules/agents/model/agent.js

## 问题

一组彼此独立的前端行为与开发体验缺陷需要收敛：默认智能体选择、恢复工具历史、提及渲染、资源选择操作栏和后端源码生效时点。

### 前端按默认标记选择智能助手

多个预置角色都具有 `is_builtin` 标记。前端按中文名称排序后选择第一个内置角色，会把深度研究选为默认，覆盖后端通过 `is_default` 表达的默认助手语义。注册先后不能约束前端重新排序后的结果。

### 恢复工具终态同步到会话历史

人工回答等待点会中断旧 Run，再由同一 Turn 的恢复 Run 完成原工具调用。恢复期间，旧 Run 的工具卡片仍来自已载入的历史投影；只更新当前 Run 的临时 item 会让卡片继续显示“已中断”，即使恢复 Run 已发布原调用的完成事件。

### 输入框与消息共用提及标签

输入框手工构造提及 DOM，消息通过 MentionTextRenderer 渲染，两处分别拥有图标分支与样式。智能体提及在输入框使用头像，消息使用 Bot 图标，同一引用在发送前后外观不同。

### 资源选择器统一状态与操作栏

少量资源的卡片列表与较多资源的弹窗选择分别维护操作栏，全选位置不一致。计数不能区分固定列表勾完当前项与动态全部，清空文本和选中态全选按钮重复占据视觉空间。

### 开发后端使用显式重启

开发 Compose 的源码监听会在编辑 Python 文件时关闭 API 与 worker，打断长连接和正在执行的任务。需要把代码生效时点交给开发者显式控制。

## 决策

本记录以 Agent 目录选择为首要 Owner，其他行为分别由会话模型、提及组件、资源配置表单与开发 Compose 拥有。各项行为保持在各自实际 Owner，避免新增共享配置、持久状态或通用抽象。首页呈现与相关取舍由[首页单屏输入入口与知识流线](2026-10-16-home-entry-screen.md)拥有。

### 前端按默认标记选择智能助手

#### 实现方案

Agent Store 在目录排序时优先放置 `is_default` 角色，再沿用内置优先和名称排序。初始化与删除当前选择后的选择逻辑先限定 `can_run`，保留有效的已有选择；否则优先选择默认角色，再取第一个可运行角色，无可运行角色时保持空选择。后端定义与返回协议保持现有行为。

这是复用现有默认标记的局部修复，无需新增配置、持久数据迁移或待裁决的架构方案，直接记录为 implemented。

### 恢复工具终态同步到会话历史

恢复 Run 的公开 `item.done` 事件若更新已载入历史中的 item，或其工具结果通过 `call_item_id` 明确关联历史调用，就同步该 item 到历史投影并重新派生消息。运行中 Run 的新 item 仍只留在临时投影，避免重复显示；未明确关联的工具输出不进入历史投影。

#### 实现方案

`agentItems.js` 负责识别并合并历史 item 的终态事件，沿用既有 reducer 和 `call_item_id` 关联规则。`sessionRuntime.js` 在消费公开流事件后同步历史消息视图；Turn 结束后的数据库快照仍负责最终完整历史。

### 输入框与消息共用提及标签

#### 实现方案

MentionToken 拥有提及的图标、头像、名称布局与样式。MentionTextRenderer 和 MessageInputComponent 都使用它；AgentMessageComponent 将当前智能体目录传入消息渲染器。智能体按稳定 ID 查找目录头像，没有目录项时按同一 ID 生成头像。输入框只保留原始 token、不可编辑边界和光标操作，在目录更新时更新标签内容，登记挂载容器，在原生剪切或替换移除标签后、重建或卸载时清理 Vue 实例。

这是在同一变更中闭合的局部渲染修复，直接记录为 implemented。模型可见文本、持久数据、提及语法和发送接口沿用已有契约。

### 资源选择器统一状态与操作栏

#### 实现方案

所有列表在同一操作栏显示状态，右侧放全选、打开选择弹窗、清空及原有资源管理操作。全部态显示“已选择全部（含新增）”，隐藏重复的全选按钮；固定列表继续显示已选与总数。清空使用带可访问名称和 tooltip 的 X 图标，保留空数组语义；点击全选保存 `all`。状态区提供直接反馈，省去重复 toast。只读配置展示状态与所选资源。

AgentRuntimeConfigForm 拥有布局与交互，agentConfigUtils 继续拥有默认值、动态全部、固定选择与不可见引用的投影。候选项较多时仍通过已有弹窗调整选择，确认结果保存固定列表。该局部修复在同一变更中闭合，无新增状态、依赖或持久化契约，直接记录为 implemented。

### 开发后端使用显式重启

#### 实现方案

开发 Compose 直接启动 Uvicorn 与现有 worker 入口，保留源码挂载，移除后端文件监听。修改后端 Python 源码后，由开发者重启相应服务；Compose 启动命令变更使用 `docker compose up -d --no-deps api worker` 应用。前端继续使用 Vite 热更新。开发操作说明由贡献指南拥有，初始化脚本提示与架构地图保持一致。

源码编辑不自动结束后端进程。Run 恢复、取消、关停超时与持久数据沿用现有 Owner 的行为。

## 替代方案

各主题下列出被评估的方案及其代价；由于问题彼此独立，不引入跨模块的统一机制。

### 前端按默认标记选择智能助手

仅调整注册顺序无法解决前端重新排序。硬编码智能助手名称或 ID 会复制后端默认定义。每次进入页面强制选择默认助手会覆盖用户主动选择，因此保留现有选择恢复规则。

### 恢复工具终态同步到会话历史

- 等待恢复 Run 完成后再刷新历史：实现更简单，但在长工具调用期间仍错误显示旧调用已中断。
- 把所有当前 Run item 写入历史投影：会把仍在执行的消息重复展示在历史与临时流视图中。

### 输入框与消息共用提及标签

只给消息补头像仍保留两份渲染和样式，后续调整会再次分叉。把整个 contenteditable 改为声明式渲染会扩大光标、输入法与选择范围的回归面；共用标签组件能保留现有编辑器边界。

### 资源选择器统一状态与操作栏

分别调整两种操作栏仍保留重复模板和不一致风险。保留选中态全选按钮会与状态信息重复，并使“全选”按钮兼具切换到固定列表的隐含行为；动态全部通过状态表达，固定选择通过已有逐项编辑或弹窗完成。

### 开发后端使用显式重启

保留重载会继续让文件编辑决定任务关停时点。增加开关或排除目录仍需维护监听策略，并不能覆盖所有影响运行的文件。因此选择移除后端监听，不增加配置或依赖。

## 后果

### 前端按默认标记选择智能助手

首次选择与失效选择回退遵循后端默认标记。浏览器已经保存的深度研究选择仍会恢复，用户手动切换到智能助手即可更新该偏好；现有会话所属智能体保持原有路由行为。

### 恢复工具终态同步到会话历史

恢复输出在公开事件到达后即可更新旧工具卡片并展示工具结果。只有明确关联的调用会跨 Run 更新；孤立输出不会按相同 `call_id` 猜测归属。

### 输入框与消息共用提及标签

输入框和消息按相同资源身份显示同一头像与名称，目录晚到或更新时同步刷新。Vue 标签实例的清理由输入框负责，整条消息的生命周期由消息组件负责。

### 资源选择器统一状态与操作栏

操作位置不随候选数量改变。用户能够区分包含后续新增资源的全部态与当前资源的固定范围。清空包含不可见历史引用，局部编辑继续保留不可见引用；配置的服务端消费沿用已有规则。

### 开发后端使用显式重启

开发者需要显式重启才能加载后端源码。首次应用启动命令会替换 API/worker 容器，执行前检查活动 Run 和后台作业。Cube 共享挂载阻塞需要独立处理；本决定仅移除源码监听引发的后端重启。

## 验证

### 前端按默认标记选择智能助手

`docker compose exec frontend node --test test/unit/agentInitialization.test.js` 通过。测试覆盖多个内置角色、有效和失效的已有选择、默认角色不可运行与没有可运行角色。原实现运行同一测试时因实际选中 `deep-research` 而非 `default-chatbot` 失败，证明回归案例能恢复目标缺陷。

### 恢复工具终态同步到会话历史

- `docker compose exec -T frontend node --test test/unit/agentItems.test.js`：13 项通过。
- `docker compose exec -T frontend pnpm run lint:check`：通过。
- `docker compose exec -T frontend pnpm run build`：通过；输出包含现存的 Vue `:deep` 与 chunk size 警告。
- `docker compose exec -T frontend pnpm run test:unit`：584 项中 583 项通过；`test/unit/messageDebug.test.js` 第 88 行失败，摘要实际为“开始查询”，断言仍期待“开始查询 | 工具: search_kb、read_file”。失败位于已有的 `messageDebug` 变更，不涉及本次文件。
- Playwright 打开目标会话 URL 后被重定向到 `/login`；独立浏览器没有该会话的登录态，因此无法取得目标页面截图或验证已登录 DOM。
- `git diff --check`：通过。

### 输入框与消息共用提及标签

`playwright-cli -s=agent-mentions run-code --filename=frontend/test/browser/mentionRendering.js` 在真实 Vite 页面挂载生产消息组件和输入组件，比较实际 DOM、头像来源、尺寸、颜色、间距与对齐。覆盖生成头像、自定义头像、图片失败占位、目录为空和更新、通过主题 Store 切换的浅色与暗色、1440px 和 768px 宽度，以及原始 ID 序列化、整体删除、其他资源图标一致性和原生替换后的实例清理。修复前同一脚本因消息未渲染智能体头像失败。

该浏览器验证使用固定目录数据，不发送真实模型请求，也不覆盖服务端历史持久化。

`docker compose exec frontend node --test test/unit/mention_utils.test.js test/unit/agentMentionConfig.test.js` 的 6 项相关测试通过。`docker compose exec frontend pnpm run lint:check`、`docker compose exec frontend pnpm run build`、在 docs 目录执行的 `pnpm run build` 与 `git diff --check` 通过。`python3 -m unittest scripts.test_verify_engineering_contracts` 的 64 项测试通过；后端 `docker compose exec api uv run --group test pytest test/unit -m "not slow"` 为 2750 passed、60 skipped。

`docker compose exec frontend pnpm run test:unit` 为 583 passed、1 failed，失败位于已有工作区变更涉及的 messageDebug.test.js，断言仍包含工具名。`python3 scripts/verify_engineering_contracts.py` 因已有 resumed-tool-history-projection 决策记录的 Owner 格式错误失败。这两项未修改，完整工作区 gate 尚未通过。

### 资源选择器统一状态与操作栏

`playwright-cli -s=agent-mentions run-code --filename=frontend/test/browser/resourceSelectionToolbar.js` 在真实 Vite 页面挂载生产表单，核对默认全部文案、X 图标可访问名称、操作位置、清空后的配置、动态新增资源、固定全选计数、弹窗确认、不可见引用保留与清空、只读展示，以及浅色/暗色和 1440px/768px 截图。原组件运行同一脚本时因默认全部未在状态区表达而失败。

`docker compose exec frontend node --test test/unit/agentConfigUtils.test.js test/unit/agentRuntimeConfigVisibility.test.js` 的 13 项相关单测通过。浏览器使用固定目录数据，不覆盖资源 API 或服务端配置持久化。

`docker compose exec frontend pnpm run lint:check`、`docker compose exec frontend pnpm run build`、在 docs 目录执行的 `pnpm run build` 和 `git diff --check` 通过。`python3 -m unittest scripts.test_verify_engineering_contracts` 的 64 项测试通过。

完整工作区仍有已有失败：`docker compose exec frontend pnpm run test:unit` 为 583 passed、1 failed，失败属于 messageDebug.test.js 的工具摘要期望；`python3 scripts/verify_engineering_contracts.py` 因已有 resumed-tool-history-projection 决策记录的 Owner 格式错误失败。这两项不属于本次选择器修改。

### 开发后端使用显式重启

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 后端直接运行且不监听源码 | 恢复 API reload 或 worker watchfiles | docker-compose.yml | 配置 unit 98 passed；最终合并配置和容器 command 回读 | 修改 Compose 前新增 guard 因 API/worker 都启用监听而失败；两种旧命令负控通过 | Passed |
| 源码文件时间变化不重启后端 | Compose 覆盖配置或运行进程仍有监听器 | 当前 Compose API/worker 进程 | 空闲时应用配置，触碰源码并等待 10 秒后，主进程 PID 与启动 ticks 均不变；API readiness 与 worker health 通过 | 旧命令由上述 unit 拒绝 | Passed |
| 开发操作与配置一致 | 文档继续要求后端热重载 | 贡献指南与初始化脚本 | 工程契约、文档 build、残留说明检索及 Bash 语法检查通过；PowerShell 只有提示字符串变更，缺少 pwsh，未执行其脚本 | 源码检索残留后端热重载说明 | Passed / Not run：PowerShell |

实际执行 `backend/.venv/bin/python -m pytest backend/test/unit/config -q`（98 passed）、`docker compose config --quiet`、`docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q`（2580 passed、58 skipped，容器缺少仓库根目录的配置用例由宿主机测试覆盖）、`python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`（64 passed）、`cd docs && pnpm run build`、`bash -n scripts/init.sh` 及相关测试文件的 Ruff check。运行中的服务通过 `docker compose up -d --no-deps --no-build api worker` 应用命令。

旧能力不存在：开发 Compose 后端不再声明 `--reload`、`--reload-dir` 或 `watchfiles` 启动包装。直接运行 Python API 模块的独立调试入口不属于此变更。

重新引入条件：另有明确隔离的开发实例 consumer，且可以证明源码编辑不会中断其他用户任务时，再裁决独立启动方式。
