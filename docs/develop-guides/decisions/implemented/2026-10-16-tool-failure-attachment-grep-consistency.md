# 工具失败、附件草稿与文件搜索一致性

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/extensions/tools/knowledge/tools.py

## 问题

知识库工具把检索异常转成普通字符串，工具结果因此记为成功，界面显示空结果。附件上传在确认时使用当前会话，期间切换会话会改变草稿归属。本地文件与 VM grep 对默认上限及恰好达到上限时的截断标记不同。

## 决策

### 实现方案

`query_kb` 让检索异常进入现有 ToolErrorGuardMiddleware，生成绑定同一调用的错误 ToolMessage，继续沿既有审计与公开投影传递；正常空结果仍是成功。SessionWorkspace 在打开附件上传框时固定目标草稿，确认始终写回该目标；当前新草稿创建正式 Thread 时跟随既有草稿迁移。UserSandboxBackend 的 grep 在路由前统一默认上限为 1000，正数显式上限保持有效；只在发现第 N+1 条匹配时标记截断，两条路径返回前 N 条。

目标是修复三处已复现行为。非目标是拆分大型组件/路由、改变 API/Schema、增加配置、迁移历史数据或重构其他知识库工具。现有非正数上限没有有效业务含义，明确返回搜索错误。

## 替代方案

- 前端识别“检索失败”字符串：依赖文案且无法修复持久工具状态，不采用。
- 为知识库新增错误协议：现有 ToolMessage 与中间件已有消费者，不采用。
- 切换会话时取消上传：需要处理未完成上传和临时文件清理，且会丢失当前上传流程；选择固定原始归属。
- 保留两种 grep 上限：相同工具输入依赖路径改变结果，不采用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 检索异常记录为失败且界面显示错误 | 吞异常成为成功空结果 | query_kb、既有错误中间件、工具结果投影 | assembled unit、工具组件和浏览器、真实 worker 链路 | 恢复吞异常导致失败状态断言变红 | Passed |
| 附件回到打开上传框时的目标草稿 | 确认时切换到其他 Thread | SessionWorkspace | 针对性 unit 与真实页面回读 | A 打开、切换 B、完成上传后确认；新草稿迁移 | Passed |
| 文件搜索返回一致上限和截断语义 | 恰好 N 条也被截断或本地无限制 | UserSandboxBackend | 文件 unit、真实 VM 与 worker E2E | 0/N/N+1、默认 1001、非法上限 | Passed |

## 后果

异常内容由现有中间件脱敏，仅公开错误类型及修复提示。附件在其他会话确认后保留在原草稿，必须通过切回原会话核验。真实 VM 与 worker 验收依赖可用 Cube 环境。E2E 只归档自身会话、删除 UUID 临时文件和新建 Workdir 中的测试文件，再删除临时 Agent 与模型供应商；保留持久审计，不递归删除可能与其他 Project 重叠的目录。

实际执行：

```bash
docker compose exec -T api uv run --group test pytest test/unit/sandbox/test_user_sandbox_backend.py test/unit/middlewares/test_tool_error_guard.py -q
docker compose exec -T api uv run --group test pytest test/unit -m "not slow" -q
docker compose exec -T api uv run --group test pytest test/e2e/test_tool_result_consistency_e2e.py -q
cd backend && .venv/bin/python -m pytest test/unit/config -m "not slow" -q
cd ..
docker compose exec -T frontend node --test test/unit/threadCreation.test.js test/unit/toolRendering.test.js
docker compose exec -T frontend pnpm run lint:check
docker compose exec -T frontend pnpm run test:unit
docker compose exec -T frontend pnpm run build
playwright-cli -s=p2-regressions --raw run-code --filename=frontend/test/browser/attachmentDraftOwnership.js
python3 scripts/verify_engineering_contracts.py
python3 -m unittest scripts.test_verify_engineering_contracts
backend/.venv/bin/ruff check backend/yuxi
backend/.venv/bin/ruff format backend/yuxi --check
backend/.venv/bin/ruff check --select I backend/yuxi
pnpm --dir docs run build
git diff --check
```

针对性后端 47 项通过；全量后端 2681 项通过、61 项跳过，宿主补跑配置测试 103 项通过。前端针对性 29 项、全量 unit 628 项通过，lint、类型检查与构建通过。工程契约及检查器 66 项、Ruff 三项检查、文档构建通过。

恢复目标缺陷的后端用例实际失败：两种检索异常的 ToolMessage 被标为成功；本地默认 1001 条未限量、恰好两条被标为截断；非正上限不能明确拒绝。修复后知识库组装测试回读错误 ToolMessage 和公开投影，正常空检索仍为成功；文件测试从临时磁盘与实际 Guest 搜索脚本回读条数、行号和截断标记。

浏览器回归在独立页面运行真实 SessionWorkspace，通过既有公开组件入口切换同一实例的会话，延迟完成上传并点击确认；缺陷代码实际报“A 的附件进入了 B 的草稿”，修复后 B 无附件、切回 A 显示原文件。浅色 1440px 与深色 390px 截图已回读。上传 API 和登录使用合成响应，不把该证据计为后端上传、解析或消息发送 E2E。

确定性 E2E 经过真实 HTTP、ARQ worker、OpenAI replay 和 Cube：模型回读两路径在上限 2 时完整、上限 1 时截断；PostgreSQL 回读同一 Turn/Run 的失败知识库工具审计与错误结果，Turn 正常完成；HTTP 下载回读生成文件字节。清理后再次检查测试文件不存在。该用例证明无权限/不可见知识库的真实工具失败链路；实际外部检索服务故障由组装 unit 注入，未执行真实外部模型或检索供应商故障探针。
