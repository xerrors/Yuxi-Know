# 会话归档统一未结束工作的判定

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/services/threads.py

## 问题

根会话承担协作树导航入口，归档必须等待整树工作结束。成员归档只需等待自身工作结束。树级与单 Thread 分别查询 Turn、Input、Run，根分支又重复执行单 Thread 判定，同一个安全条件存在两套实现。

## 决策

### 实现方案

[Thread service](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/services/threads.py)决定检查范围和锁序。根归档先锁 Project，再按 Thread ID 锁同用户、APP 的树成员；成员归档只锁自身。[Session repository](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/repositories/sessions.py)通过同一个查询判断范围内是否存在 pending Input、未结束 Turn、未终态 Run 或运行清理责任。检查通过后只归档指定 Thread，不取消工作或改动历史。

## 替代方案

- 保留两套判定：根和成员的状态演进需要同步维护，根路径重复查询。
- 仅保留单 Thread 检查：根会话会隐藏仍有工作的后代。
- 归档时取消整树：将展示操作变成执行控制，违反显式停止语义。

## 后果

根归档保留后代入口，空闲成员则可以在其他成员仍有工作时独立归档。Project → 有序 Session 锁序与创建成员、项目删除保持一致，输入受理不能越过归档判定。

归档检查覆盖事务当下已受理的工作，不冻结后代。根归档后仍为 active 的成员可以接收新的用户工作，根不会自动恢复为 active；这类树通过归档入口重新访问。若产品要求任何后代工作都持续出现在活动导航，需要另行确定根恢复或整树归档的行为，不能由未结束工作查询暗中改变。

## 验证

真实 PostgreSQL 归档测试覆盖根与成员的运行、人工等待、排队和清理场景，独立回读被拒绝的目标仍为 active；结束工作后归档成功。成员场景同时回读根仍 active、Run pending、Turn running，证明检查范围没有扩大到其他成员。关联项目删除继续拒绝未完成工作。

实际命令（数据库是临时 PostgreSQL 的独立测试库）：

```bash
PYTHONPATH=backend python -m pytest backend/test/integration/services/test_project_thread_archive.py -q -p no:cacheprovider
docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_session_thread_status.py -q -p no:cacheprovider
```

PostgreSQL 十一项与 Thread 状态 unit 十一项通过。公开 HTTP 和完整 worker 回归由相关链路测试补充，不以此局部结果替代。

旧能力不存在：归档入口不再分别调用 Turn、Input、Run 三套检查；树级专用工作判定被统一的授权会话范围查询替代。

重新引入条件：出现具有不同持久业务语义的归档对象，且无法用明确的检查范围表达。
