# 来源标注模型与内容范围

状态：implemented
类型：feature
Owner：backend/yuxi/modules/agents/services/references.py

## 问题

来源标注沿用回答模型，容易继承高思考成本；代码、公式和 Chat 组件也参与输入和标注定位。

## 决策

### 实现方案

系统 Options 的 `reference_model` 由超级管理员配置，空值明确沿用快速响应模型。选择器可清空以恢复该策略；关闭思考使用已有模型请求参数配置，不新增跨供应商能力探测或每次选模弹窗。来源 service 在新标注调用时读取当前配置，不再依赖历史 Run 的模型快照，最终回答的 Turn/Run 归属与成功结果重放保持不变。该决定部分取代[Turn 按需标注来源](2026-10-09-turn-reference-annotations.md)的模型选择与内容范围。

后端解析 Markdown，仅把正文、图片、表格以原始行号发送给模型，并拒绝覆盖代码、公式、HTML 或 Chat 组件的范围。表格保留分隔行；任务列表文字属于正文。未闭合的美元符号块公式按前端 KaTeX 的公式语义排除。历史持久标注读取时也过滤排除范围，不修改原始回答和历史数据。

前端 renderer 在插件生成 checkbox HTML 前标记允许挂载来源的正文与表格行，紧凑列表使用正文范围而非整个列表项。来源装饰只选择这些位置，并拒绝跨越排除块的旧范围；通用原始行映射保留用于文档定位。复用 Chat 组件时保留其排除属性。超时提示建议在设置中选择关闭思考或降低思考强度的来源标注模型，不推断具体超时原因。

## 替代方案

- 每次弹窗选择模型：增加所有用户的重复操作和配置负担。
- 对未知供应商强制发送关闭思考参数：可能被拒绝或忽略，复用现有模型配置更直接。
- 分批、摘要或新增能力探测系统：没有本次验收需要的证据，不引入。

## 后果

快速模型也可能启用思考；管理员须选择非思考模型，或使用供应商支持的现有请求参数关闭思考。修改模型请求参数也影响使用该模型配置的其他任务。本功能不宣称自动关闭未知模型的思考，也不承诺固定耗时。

回答侧排除内容减少输入，来源正文不做摘要、分批或静默截断。60000 字符预算、90 秒调用期限、当前知识库可见性校验与原文摘录校验继续生效。图片仅标注可确认的来源或图注，不将文本调用解释为对图片像素的核验。没有引入依赖或 Schema 版本变化。

## 验证

- `docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_turn_references.py test/unit/config/test_options.py -q`：53 passed。覆盖默认/显式模型配置、原始行号、完整表格、任务列表、排除内容和跨块范围拒绝、超时提示与原回答保持不变。
- `docker compose exec -T -e TEST_BASE_URL=http://localhost:5050 api uv run --no-sync --group test pytest test/integration/api/test_turn_references.py -m 'not slow' -q`：13 passed、1 deselected。真实 HTTP、模型 wire 与 PostgreSQL 回读证明配置选择、快速模型策略、既有关闭思考参数透传、非管理员拒绝、失败重试及旧标注过滤。fixture 只清理自己创建的记录，避免无关共享 Workdir 清理；模型和快速模型配置在结束时恢复。
- `node --test frontend/test/unit/markdownReferences.test.js frontend/test/unit/markdown_preview_fallback.test.js`：14 passed。覆盖任务列表 checkbox 与原生 HTML 区别、代码/公式/组件排除、未闭合公式、列表与表格范围以及通用行号不变。
- `playwright-cli -s=references run-code --filename=frontend/test/browser/referenceContentScope.js`：真实开发页面挂载产品 MarkdownPreview，读取 DOM 验证五处允许标注、排除块零标注、Chat 组件内部文字零标注、表格末行与原始第 25 行定位。管理员设置选择与清空经真实 HTTP 保存验证，浅深色和 1440/768px 页面留有截图。
- `docker compose exec -T api uv run --no-sync --group test pytest test/unit -m 'not slow' -q`：3073 passed、107 skipped。`cd frontend && pnpm run test:unit`：790 passed。容器前端全量有 9 项模块边界测试失败，其镜像内 `eslint-boundaries.js` 与工作区不一致；工作区当前配置的全量结果单独通过。前端容器 lint/build、工作区 lint、后端三项 Ruff 与 `git diff --check` 通过。
- `cd docs && pnpm run build`、两份受影响决策记录的相对链接检查及 `python3 scripts/verify_engineering_contracts.py` 通过；`python3 -m unittest scripts.test_verify_engineering_contracts`：66 passed。
- 真实供应商模型延迟与关闭思考效果未执行探针；确定性 wire 仅证明请求参数与输出校验，不替代供应商行为验证。
