# 对话搜索返回完整会话投影并支持标题匹配

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/conversation_service.py

## 问题

`GET /api/chat/threads/search` 在 `search_threads_view` 中手工拼装结果 dict，缺少响应模型 `ThreadResponse` 的必填字段（`workdir_path` 等），任何命中都会在 FastAPI 响应校验处抛错返回 500；该端点此前无任何集成测试覆盖，缺陷长期未被发现。同时仓储检索只 join 消息正文，标题命中的会话完全搜不到，与"全局搜索"的产品语义不符。

## 决策

### 实现方案

服务层放弃手拼 dict，复用会话列表的 `_serialize_thread` 投影并批量附加 `thread_status`（经 `get_latest_top_level_runs_for_threads`，避免逐会话查询），结果字段与 History 列表同口径、满足 `ThreadResponse` 校验。仓储层把消息正文检索改为 `LEFT OUTER JOIN messages` 并加标题 `ilike` 条件：标题命中而正文无命中时返回会话且 `matched_count=0`、`snippets=[]`，不伪造消息命中数；方法按新语义更名 `search_conversations`。可见性仍由仓储既有的 uid/共享谓词限定，跨用户标题与正文都不泄露。

## 替代方案

- 给手拼 dict 补缺失字段：拒绝。字段清单与 History 列表各自演化必然漂移，序列化 Owner 应是同一个 `_serialize_thread`。
- 标题检索另起一个 UNION 查询：拒绝。命中口径（计数、片段、分页）需要两套实现保持一致，单查询 outer join 足够。

## 后果

搜索端点从"命中即 500"变为可用；标题命中的结果 `matched_count=0` 且无片段，前端按既有契约展示。排序口径（最近活动）与列表一致。仓储方法更名后，调用方仅服务层一处，无外部 API 变化。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 搜索命中返回满足 ThreadResponse 的完整投影 | 手拼 dict 缺字段 → 任意命中 500 | `search_threads_view` 复用 `_serialize_thread` | `test/integration/api/test_thread_search.py::test_thread_search_content_match_returns_full_thread_fields`（真实 HTTP）；`test/unit/services/test_conversation_search_serialization.py` | 在未含修复的服务代码上复跑同一请求实测返回 500 | Passed |
| 标题命中可搜索且只命中用户可见会话 | inner join 漏标题；跨用户泄露 | `search_conversations` outer join + 既有可见性谓词 | `::test_thread_search_matches_conversation_title_without_message_hit`、`::test_thread_search_does_not_leak_other_users_threads`、`test_search_conversations_title_match_stays_within_user_and_agent_scope`（单测） | 基线实现（仅正文 inner join）下标题用例实测搜不到目标对话 | Passed |
| 序列化/仓储单测与全量 unit 无回归 | 既有列表行为漂移 | `test/unit/storage/test_conversation_repository.py`、全量 `test/unit` | 定向 18 passed；真实上游 lock 镜像全量 `pytest test/unit -m "not slow"` → 2469 passed / 62 skipped；`ruff check`/`format` 干净 | 不适用 | Passed |

未验证范围：前端搜索弹窗的真实页面验证 `Not run`（无前端改动）。
