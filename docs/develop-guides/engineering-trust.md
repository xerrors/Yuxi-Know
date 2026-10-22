# 工程信任系统

Yuxi 把 Agent 或开发者提交的实现视为待证伪候选。完成状态需要明确 Owner、真实系统事实、与风险匹配的 oracle、只读 gate 和可问责语义 Review 共同证明。提交者自述、测试数量和一次手工演示不能单独形成完成证据。

从请求、提案、实现、证据到收敛的日常顺序由 [Yuxi Spec Loop](./spec-loop.md) 维护；本页只拥有信任闭环与证据等级。

## 权威模型：主张在语义 Owner 处闭合

Yuxi 不维护可独立编辑的中央 risk/claim inventory，也不要求 claim ID。中央清单会复制源码、数据约束、测试和 workflow 已经拥有的事实，最终形成需要人工同步的第二真相。

一个重要工程主张由最接近行为的语义 Owner 拥有，并在该 Owner 周围形成可追踪闭环：

| 闭环部分 | 当前权威 |
|---|---|
| 意图与外部结果 | owning 用户/协议文档、API 契约或决策记录中的问题与决定 |
| 状态与副作用 | 实际写入代码、repository、数据约束及明确的 commit/publication 边界 |
| 独立 oracle | 最接近风险、且与实现具有不同失败方式的 unit、integration、E2E、replay 或真实探针 |
| 负向案例 | 恢复目标缺陷或制造非法状态后会因正确原因失败的测试 |
| 执行后果 | 实际选择该 oracle 的阻断 workflow，或对语义取舍负责的 Reviewer |
| 理由与代价 | 对应的 tracked decision record；当前行为仍以语义 Owner 为准 |

这些材料可以分布在各自正确的位置，但必须能从一次变更追踪到同一个行为。改变持久状态、信任边界、长生命周期、权限、公开兼容或模型体验时，PR 直接用自然语言列出受影响主张及其 Owner、观察边界、oracle、负向案例和未验证范围；不得用中央登记完成来替代真实闭环。

## 派生审计投影

`scripts/verify_engineering_contracts.py` 从当前 Owner-local 材料检查 decision lifecycle、workflow 接线、路径覆盖、分层 AGENTS 指令的链接/标题/预算和可机械判断的架构边界，并可临时输出审计投影：

```bash
python3 scripts/verify_engineering_contracts.py --report
```

该输出由仓库事实重新生成，不提交、不手工编辑，也不反向定义事实。删除投影后应能从同一代码、测试、decision 和 workflow 得到相同结果。Verifier 只证明引用、接线和部分边界检查真实存在；router/frontend 边界检查只覆盖静态可判部分，service 层事务、锁与 lease 语义仍由真实 PostgreSQL integration 证明。它也不判断目标是否值得、测试断言是否正确、oracle 是否真正独立、远端是否把检查设为 required，或某个 diff 是否被错误归类为 trivial。这些语义仍由 Reviewer 结合真实系统证据裁决。

## 证据等级

| 证据 | 证明什么 | 不能替代什么 |
|---|---|---|
| Unit | 纯逻辑、边界值、状态转换和失败分支 | PostgreSQL、Redis、HTTP、worker 或浏览器真实语义 |
| Integration | 真实 API、认证、事务、锁和服务副作用 | 完整用户/模型 journey 与外部 provider 漂移 |
| E2E | Compose 中的 shipping entry、worker、SSE、文件/对象和最终业务结果 | 每个局部分支与确定性故障注入 |
| Deterministic replay | 不依赖真实 provider 的 assembled-path 回归 | 实时模型/provider 行为 |
| Real probe | 外部模型、浏览器或部署实例的现实校准 | 低噪声、每 PR 都可执行的阻塞 gate |
| Semantic Review | 目标、取舍、oracle 独立性和 expected-output 语义 | 可机械判断的格式、引用、选择器和构建错误 |

每个 guard 都要证明目标缺陷会让它变红。Snapshot、fixture 和 expected output 只能显式更新，CI 只读验证。随机/并发测试失败必须保留可重放输入、seed 或数据库事实，不能用重试掩盖。

## 决策记忆

[decisions/](./decisions/README.md) 保存代码和当前文档无法表达的问题、why、替代方案、代价与验证。它不保存 Agent 推理流水账、Review 过程或迁移 checklist。`implemented/` 是当前决定，`proposed/` 与 `rejected/` 不构成运行时权威，`archived/` 是冻结历史。

普通代码注释和正式文档仍只描述当前行为、Owner、失败、时序和安全用法；不要把 decision rationale 复制到多个位置。

## Gate 的运行与维护

```bash
python3 scripts/verify_engineering_contracts.py
python3 -m unittest scripts.test_verify_engineering_contracts
```

Gate 必须只读、失败可诊断、拥有明确 Owner，并保持有限延迟。低成本只读检查（`trust.yml`）在每个 PR 运行；它是否阻止合并由 GitHub 分支保护的 required 设置决定，workflow 本身不保证这一点。真实 Compose integration/E2E（`system-tests.yml` 等按路径触发）只在匹配高风险范围时运行。高风险 Agent 主链路使用无外部密钥的 deterministic assembled-path E2E 阻断，`real-provider-probe.yml` 手工探针负责外部 provider 校准；两者不能互相冒充。Workflow、selector、skip 或 expected-output 更新都按生产代码审查；长期 flake、误报、绕过或无 consumer 的 gate 应及时修复或退役，禁止用新增规则掩盖既有缺陷。

运行时当前事实属于 `ARCHITECTURE.md`、对应代码 Owner 与测试；本页不复制 readiness、Run 或 checkpoint 契约。相关非显然取舍保存在 [工程决策记录](./decisions/README.md) 的聚焦 implemented records 中，审计时从这些局部 Owner 派生，不维护另一份手工状态表。

## 事故反馈

只有已经逃逸且达到项目复盘门槛的高影响缺陷才形成正式 [postmortem](./postmortems/README.md)。每个符合门槛的事故有 Owner，说明真实影响、因果链、为什么既有安全网漏过，以及新增或修正的 reproducer、oracle、gate、decision 或 standing order。学习需要主动实现和 Review，不会自动发生；普通缺陷仍保留与风险相称的回归证据，但不强制制造事故文档。
