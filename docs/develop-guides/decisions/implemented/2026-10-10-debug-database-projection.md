# 调试面板直接投影数据库消息

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/agents/repositories/sessions.py

## 问题

调试面板合并普通聊天历史、实时消息和持久审计，模型记录的位置受普通历史影响，正文也可能被实时投影覆盖。用户无法通过面板核对数据库中的消息事实。

## 决策

### 实现方案

超级管理员审计接口读取同一 Thread 的全部持久 Message，包含尚未关联 Run 的用户输入。Repository 按 Run 创建时间、Run ID、操作 sequence、Message ID 返回稳定顺序；Run 内用户输入排在操作前，其他无 sequence 消息排在操作后并按 Message ID 排列，无 Run 消息使用自身创建时间。保留最新 500 条上限和现有授权边界。

Service 按真实角色序列化用户、系统、模型和工具，并按白名单保留普通失败消息的错误类型与信息。前端直接展示接口数组，不合并普通历史或 SSE，不用普通历史窗口限制调试记录。Run 分组仅增加导航；用户使用绿色胶囊，模型、工具等记录使用不同的主题颜色和文字。读取失败显示已有数据库快照及错误提示。

## 替代方案

- 修正混合列表排序：仍存在正文被实时状态覆盖和聊天窗口限制调试事实的问题。
- 全部按 wall-clock 排序：无法保留操作 sequence，对乱序或同时间记录也缺少明确顺序。
- 另建调试接口：重复现有超级管理员读取边界，没有当前消费者需要保留混合模式。

## 后果

500 条窗口同时包含用户消息与审计，超限提示保留。正文在数据库提交并由面板读取后更新；普通聊天继续使用独立的实时投影。移除前端审计与聊天历史的拼接函数及其专有测试，数据库顺序由真实 HTTP 测试证明，面板与接口一致性由浏览器 replay 证明。工具与系统正文可在概览查看，类型使用文字和主题颜色共同区分。

## 验证

- `docker compose exec api uv run --no-sync --group test pytest test/unit/services/test_session_message_audits.py test/integration/api/test_debug_message_projection.py test/integration/api/test_chat_router.py -k 'audits or debug_messages' -q`：4 passed。真实 HTTP 与 PostgreSQL 证明操作 sequence 优先于插入顺序和 wall-clock，包含无 Run 输入和系统消息，500 条截断与授权边界仍成立；逐行回读数据库核对正文和 sequence。
- `playwright-cli -s=debug-projection run-code --filename=frontend/test/browser/messageDebugProjection.js`：基础投影路径 Passed。真实 Vite 页验证接口顺序及正文与 DOM 一致、类型胶囊、工具筛选、搜索、工具详情、加载、空态、读取失败保留快照及浅色、暗色。375px 只证明胶囊可见，页面壳仍存在导航挤压与裁切，完整窄屏可用性未通过。该浏览器用例使用确定性接口 replay，不替代真实 PostgreSQL integration。
- `playwright-cli -s=organize-debug run-code --filename=frontend/test/browser/messageDebugProjection.js`：完整脚本 Passed，包含空正文普通失败消息的错误分类、筛选与详情验证。
- `docker compose exec frontend pnpm run lint:check`、`docker compose exec frontend pnpm run test:unit`、`docker compose exec frontend pnpm run build`：Passed，531 个前端测试通过，build 包含已有 CSS 与 chunk warning。
- `docker compose exec api uv run --no-sync --group test pytest test/unit -m "not slow" -q`：2628 passed、55 skipped；跳过项仍为容器内不可读取的仓库拓扑检查，不计为通过。
- `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`：Passed，64 个 verifier 测试通过。
- `uvx ruff check backend/test/integration/api/test_debug_message_projection.py backend/test/integration/api/test_chat_router.py backend/yuxi/modules/agents/services/checkpoint_messages.py backend/yuxi/modules/agents/repositories/sessions.py`：Passed。
- `cd docs && pnpm run build`：Passed。

常规 `uv run` 在现有容器尝试重新构建 editable 包时因 `yuxi.egg-info` 权限失败；后端验证使用容器已安装的环境加 `--no-sync`。数据库内容读取变更不涉及 worker 执行或模型策略；真实外部模型与 worker E2E 未执行。

`docker compose exec -T api uv run --no-sync --group test pytest test/integration/api/test_debug_message_projection.py test/integration/api/test_chat_router.py test/integration/api/test_checkpoint_state_view.py -q` 的集成复核在 fixture 准备阶段出现 24 errors：PostgreSQL 进程异常退出并进入恢复，未到达业务断言。上列 HTTP Passed 来自已记录的成功验证；当前运行环境未完成这组复核。
