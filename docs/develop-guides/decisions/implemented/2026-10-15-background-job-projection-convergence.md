# 后台作业内部实体与观察投影收敛

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/background_jobs/service.py

## 问题

后台作业登记与取消把持久 ORM 记录先序列化，再按另一份默认字段重建 BackgroundJob 对象。该对象没有独立行为或事实来源，重复状态、租约和默认时间定义。列表先构建带结果详情的响应再删除结果，内部参数也先进入字典再删去。

## 决策

### 实现方案

内部登记、查找与取消直接返回 repository 记录，删除重复 dataclass 和 from_dict。HTTP 观察响应由记录直接按公开字段白名单生成；列表明确不生成结果摘要。公开取消标志在 HTTP 边界转换为布尔。执行、状态、lease、错误清理和事务 Owner 保持在原 repository/worker。

## 替代方案

- keep：保留重复对象和状态默认值，拒绝。
- narrow：缩小 dataclass，仍需 ORM→dict→对象往返，拒绝。
- replace：引入另一套通用 DTO 框架，扩大维护面，拒绝。
- remove：内部复用持久记录，只在公开边界序列化，采用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 登记、去重、取消和 Owner 返回同一记录事实 | 转换复制默认状态或丢字段 | JobTracker / repository | unit、真实 PostgreSQL、HTTP | 记录身份及时间类型回读；恢复先构建详情再删结果的逻辑必须失败 | Passed：backend unit 2654 passed；真实 PG repository 24 passed；HTTP 与 worker 恢复 7 passed |
| 列表不生成完整结果且不泄露执行参数 | 先构建详情再丢弃 | BackgroundJobRecord | unit、真实 HTTP | 大结果不调用详情构建；内部字段不可见 | Passed：unit 精确负控；HTTP 详情脱敏与取消布尔回读 |

旧能力不存在：重复 BackgroundJob dataclass、from_dict 及内部 ORM→dict→对象往返不再存在。

重新引入条件：内部消费者确需独立语义的值对象且直接字段读取不能满足时，经单独决策引入。

## 后果

HTTP 响应字段和错误脱敏保持一致。内部时间保留 datetime，不通过字符串往返；不修改持久 Schema。

验证环境：真实 PostgreSQL 使用独立测试库，Redis 使用独立实例，API 与 ARQ worker 使用隔离进程。`test_background_job_worker_path.py` 先在 worker 停止时制造投递失败，再启动正式 worker 装配并回读 Job 与领域数据集的最终状态；两项恢复/失败 Hook 检查与 `test_background_jobs_router.py` 的五项 HTTP 检查通过。文档入库例程依赖外部 embedding，本记录未执行该项。
