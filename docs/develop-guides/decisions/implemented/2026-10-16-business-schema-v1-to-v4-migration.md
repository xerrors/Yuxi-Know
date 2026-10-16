# 部署数据库 business v1 到 v4 的直接调整

状态：implemented
类型：architecture
Owner：docs/advanced/deployment.md

## 问题

现有部署数据库为 business v1、knowledge v1，而当前代码只接受当前 Schema 版本。用户要求保留现有代码并直接把数据库调整到 v4，不在代码中加入历史迁移脚本。

## 决策

### 实现方案

现有部署数据库已直接调整为 business v4、knowledge v1；应用代码和 `schema-init` 不包含 v1 到 v4 的迁移函数或版本分支。`schema-init` 仅在确认空库时建立当前基线，对当前版本无操作，对其他已版本化或未版本化旧库失败关闭。数据库备份保留可恢复副本。

本次数据调整保留旧 `tool_calls` 记录并改名为 `tool_calls_v1_archive`；仅在结构化输出已存在时清空重复的 `tool_audit` 正文；移除当前代码已退役的协作列；建立当前工具结果约束和活动 Run 唯一索引。后续部署代码不携带这些操作的自动执行入口。

## 替代方案

- 在 `schema-init` 中增加可复用 v1→v4 脚本：与直接修改实际数据库、保持应用迁移代码精简的要求不符，拒绝。
- 只修改版本行：不建立 v4 约束和索引，无法使数据符合当前 Schema，拒绝。
- 清空并新建数据库：丢弃现有数据，拒绝。

## 后果

当前部署数据库可由现有 API、Worker 和 schema-init 使用；其他 v1 数据库不会被当前程序自动升级，必须由部署侧安排直接数据操作并先备份。业务表之外的已退役协作列可从活动库移除，完整 dump 保存迁移前状态。迁移失败时不得只修改版本号绕过 Schema 校验。

## 验证

- 迁移前完整 PostgreSQL dump：`/tmp/yuxi-schema-v1-before-v4-20261016.dump`；在 PostgreSQL 容器内由 `pg_restore --list` 验证可读，SHA256 `426066c05c5a94fdf5a2cdbf55985d01fadccdf22e221d01f47f17bec342b023`。
- 实际数据库回读：`business=4, knowledge=1`；`tool_calls_v1_archive` 保留 1,695 行；迁移完成时 1,648 条结构化工具结果保留，旧 `tool_audit` 正文清空；结果约束与活动 Run 唯一索引有效；退役列为 0。
- API 与 Worker 重启后，`/api/system/ready` 返回 `ready`。最终代码中的 `schema-init` 对当前 v4 无操作，对旧版本仍拒绝；对应入口 unit 与 PostgreSQL integration 覆盖该失败边界。
