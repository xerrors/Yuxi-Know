# 前端模块公开入口与跨模块边界

状态：implemented
类型：architecture
Owner：frontend/eslint-boundaries.js

## 问题

前端模块之间通过 `@/modules/<domain>/model/...` 和 `@/modules/<domain>/ui/...` 直接引用内部文件。审计统计到 34 组、101 处跨模块导入，其中 98 处使用别名、3 处使用相对路径；ESLint 只检查 app/pages/shared/apis 的上下方向，没有限制模块之间的内部路径。模块的可用 API 只能靠阅读源码推断，移动内部文件容易在无关模块产生隐式破坏。

## 决策

流程说明：本变更是对既有前端架构审计所列边界的直接收敛，没有待裁决的产品取舍或持久化契约；实现、替代方案与验证在同一变更中闭合，因此按同一变更内生效的 implemented 记录。

### 实现方案

- 每个 `src/modules/<domain>` 增加 `index.js`，作为模型与用例的公开入口。它只导出 store、校验器、纯函数和稳定常量；不导出 Vue 组件。没有跨模块模型 API 的模块保留 `export {}`，让入口存在且可继续扩展。
- `src/modules/<domain>/ui/**/*.vue` 是公开 UI 面。跨模块组件按文件导入，不建立 UI barrel。
- 跨模块允许两种路径：
  - `@/modules/<domain>`：模型、store 与纯函数。
  - `@/modules/<domain>/ui/**.vue`：公开 Vue 组件。
  - `@/modules/<domain>/model/...`、`ui.js` barrel、其他内部路径均拒绝。同模块内部深导入保持允许。
- `frontend/eslint-boundaries.js` 增加 `moduleEntry` 规则，解析别名、相对路径、`export ... from` 和动态导入；`frontend/AGENTS.md` 与 `ARCHITECTURE.md` 记录同一约定。
- 55 处跨模块模型导入（包含原先 3 处相对路径）改为从 `index.js` 导入；46 处组件导入保留按文件路径。`session/model/toolIcons.js` 承接工具图标纯查询，UI 注册表只做同模块再导出，避免模型入口反向依赖 UI。`agents/model/agent.js` 与 `session/model/chatUI.js` 的持久化存储增加 `localStorage` 未定义时的守卫，使公开入口可以在 SSR/测试环境加载。

### 为什么不使用单一 barrel

最初将模型和 UI 一起从 `index.js` 重导出。构建验证显示主入口从 1,248.95 kB 增至 3,406.89 kB，并使 `AgentEditModal` 的动态导入失效，因为任何模型导入都会加载整个领域的组件。该方案被拒绝；UI 保持按组件导入，模型入口只包含非组件 API。

## 替代方案

- 单一 `index.js` 同时导出模型和组件：边界最简单，但破坏代码分割和动态导入，实测主 chunk 增长约 2.7 倍，不采用。
- 把跨模块共享 UI 移入 `shared/ui`：长期可行，但涉及大量组件搬迁、样式和测试路径变更；本变更先明确公开面，不为边界做无关搬迁。
- 只写约定、不增加 ESLint 规则：无法阻止后续重新直达 `model/`，不采用。
- 对 app/pages 也强制公开入口：app/pages 是装配层，当前保留其按需深导入；若未来需要统一，另加独立规则。

## 后果

新增跨模块模型 API 时必须在 `index.js` 显式导出；新增公开 UI 组件只要位于 `ui/**` 即可按文件导入。模块内部文件移动不再影响其他领域，只要公开入口保持不变。UI 组件不会被领域 barrel 提前加载，路由和动态导入的代码分割保持原样。空 `index.js` 是显式占位，不代表该领域已有跨模块模型 API。

## 验证

旧能力不存在：跨模块 `@/modules/<domain>/model/...` 直达、跨模块相对路径直达和 `ui.js` barrel 均不存在；`moduleEntry` 规则和 `frontendBoundaries.test.js` 会拒绝重新引入。

重新引入条件：只有公开 UI 面需要批量重导出且构建证明不会破坏代码分割时，才评估 UI barrel；模型入口继续只导出非组件 API。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 跨模块模型导入经过公开入口 | 重新直达 `model/` 或相对路径 | frontend/eslint-boundaries.js | `pnpm run lint:check`、边界 unit | `modules/session → modules/agents/model/agent` 被拒绝 | Passed |
| 公开 UI 组件仍可按需加载 | UI barrel 拉平 chunk、动态导入失效 | modules/*/ui、Vite build | `pnpm run build` | 主 chunk 回落至 1,253.02 kB，无 `INEFFECTIVE_DYNAMIC_IMPORT` | Passed |
| 同模块深导入和页面装配不被误拒绝 | 规则误伤 | frontendBoundaries.test.js | 19 项边界测试 | 同模块 `model/agent`、页面 `ui/SessionWorkspace.vue` 保持通过 | Passed |
| 公开入口在无 `localStorage` 环境可加载 | SSR/unit 导入 store 失败 | agents/model/agent.js、session/model/chatUI.js | `pnpm run test:unit` | 无 `localStorage is not defined` | Passed：779 项 |

- `pnpm run lint:check`：通过。
- `pnpm run build`：通过；主入口 1,253.02 kB（变更前 1,248.95 kB），无新增动态导入失效警告。
- `pnpm run test:unit`：779 passed。
- 未执行浏览器 E2E；本次改动集中在 import 路径、公开入口和 ESLint 规则，真实页面行为未改变。
