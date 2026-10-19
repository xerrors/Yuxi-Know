# 核心测试前提与异步等待收敛

状态：implemented
类型：testing
Owner：backend/test/e2e/e2e_helpers.py

## 问题

输入、附件、Skill 授权、取消与恢复测试需要独立资源和准确的异步观察边界。重复的用户生命周期遗漏归档会话清理；Turn 终态、Run 运行时清理、模型进入阻塞点和文件完整发布分别表达不同事实，重复轮询容易使完成条件漂移。

## 决策

### 实现方案

普通用户的创建、登录和按用户回收统一复用已有 `standard_user` fixture。它由根已注册的 `test/support/permission_convergence.py` 提供，供 API 与 E2E 消费；先删除本例唯一用户的会话、Input、Turn、Run、消息及 Project Workdir，再删除用户身份。普通用户 E2E 删除手写身份生命周期；跨身份 Agent 使用明确授权的 bound Skill，内置发布内容仍以正式 app-init 产物为测试对象。

`e2e_helpers.py` 拥有 Input 消费、Turn 终态与 replay 阻塞点等待。Input 与 Turn 查询校验目标归属，HTTP 查询和轮询共用总预算，超时只报告目标 ID 与最后状态。Turn 等待返回 completed、failed 或 cancelled，由调用方断言本例结果。删除附件前复用 `live_api_cleanup.py` 的历史 Run 清理检查，并单次回读原 Run 的 completed 与清理标记；不再维护重复的清理 SQL 轮询。该清理检查的总预算覆盖数据库连接与查询。

阻塞模型复用现有 started/release 协议，文件写入先使用同目录临时文件再原子改名；释放本例阻塞信号放在 `finally`。Skill 模型准备复用已有缓存 TTL helper。保留 HTTP、不可变 Receipt、输入消费归属、取消后无正式消息、文件与对象字节等独立业务断言。

范围仅为 P0、P1：不改变产品 API、持久状态机、权限、工作流、套件选择或测试运行器。验证使用独立 Compose project、数据库、Redis、对象存储和数据子目录，复用现有 Cube 节点与正式模板。

## 替代方案

- 保留调用方重复的准备和轮询：无法由同一个 Owner 维护身份清理与完成条件。
- 新建通用等待或场景框架：现有具体 helper、fixture 和重放协议足够，额外配置与生命周期没有消费者。
- 同时调整 CI 分组与选择器：属于 P2，不纳入该决定。

## 后果

调用方删除重复 Input/replay 轮询、附件清理 SQL 和两套普通用户生命周期。共用等待只证明状态边界，业务结果仍由独立断言拥有。错误归属、目标消失、失败终态和超时保持不同含义，不能用一个通用“完成”掩盖。

每组稳定性验证使用 20 次串行独立资源，不加入日常 CI 重复执行，也不证明所有并发交错。managed Workdir 按日期父目录和 Project 叶目录分配；清理移除本例叶目录与文件，允许空日期骨架保留。专用槽位结束时回收本槽位 VM 与全部数据，其他节点实例不在清理范围内。

## 验证

真实测试在同一专用 Compose 拓扑执行，没有重试或 skip。最终 fixture 的 API 与跨身份组合每批结束后，独立 SQL 回读会话、Input、Receipt、Turn、Run、attempt、消息和附件记录均为 0。

| 范围 | 实际结果 |
|---|---|
| 输入并发与优先队列 | 单独 11 / 22 通过，组合与逆序各 33 通过；API 与 Cube 地址故意不可达时另有 33 通过 |
| 公开附件与 bound Skill API | 单独 6 / 15 通过；组合与逆序各 21 通过 |
| 普通用户、Key 与 worker Skill | 普通用户单独 2 通过；跨身份组合与逆序各 7 通过，逐批业务记录归零 |
| 输入、取消与恢复 E2E | 生命周期单独 17、组合 20、逆序 20 通过；事件、恢复、Skill 与跨身份组合、逆序各 13 通过；最终定向回归 3 通过 |
| 真实 PostgreSQL 清理 | `pytest test/integration/services/test_live_api_cleanup_run_rows.py -q`：12 通过 |
| 最终版本稳定性 | 环境变量文件发布 / 更新 / 暂停唤醒 20/20；附件待消费快照 / 取消 / 清理后删除 20/20；零失败、零重试、零 skip |

负控恢复提前发布最终空文件时，真实 Cube 用例在“未写完不能发布”断言失败；独立 replay 进程延迟接收请求时，等待保持未完成，进入阻塞点后模型响应仍未结束，释放后 SSE 完整结束。独立事务延迟旧 Run 清理，移除清理标记检查即提前放行并触发数据库断言失败；移除请求总期限时，真实表锁用例因未按期抛错而失败。移除 Turn 归属检查后，错误 Thread / Turn 的两项反例失败。普通用户手工生命周期的零残留回读失败暴露六条归档链路；复用 fixture 后各批回读归零。

最终回读确认本例业务记录、输入隔离 Schema、附件临时对象、Project Workdir 与 Cube fixture 用户目录均为 0。空日期父目录保留且内部为空；本槽位基线管理员 VM 在槽位回收时删除，控制面逐 ID 返回 404，用户 metadata 中没有本槽位或 Cube fixture 实例。

`docker compose exec -T api uv run --group test pytest test/unit -m "not slow" -q`：2921 通过，99 个配置用例因容器缺少仓库根文件跳过；宿主 `uv run --project backend --no-sync --group test pytest backend/test/unit/config -q`：159 通过，覆盖全部跳过用例。相关 support unit 为 36 通过。

工程 verifier 与其 66 个单测在仅含本决定改动的干净提交快照中通过；相对链接检查、docs build 与 `git diff --check` 通过。Ruff 0.16.4 检查的本轮新增与修改行没有新增问题；`live_api_cleanup.py` 保留 HEAD 已存在的五处 E501。

只读 GitHub 核验确认 `develop/0-8-0` 没有分支保护与适用规则，未配置 required checks；保护设置没有修改。没有执行新的远端 CI，不作 CI 耗时或全量门禁结果的新增主张。P2 保留为未实施范围。
