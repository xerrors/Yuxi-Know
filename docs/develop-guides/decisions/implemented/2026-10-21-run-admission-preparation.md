# 收敛 Run 执行准入拒绝与清单准备

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/services/runner.py

## 问题

输入格式、持久消息、执行用户、目录授权、恢复输入及运行清单有不同的拒绝原因。为每个判定复制失败结算参数与 return，会分散业务错误和生命周期责任。消息与用户读取属于 PostgreSQL；Workdir 授权既查询 Thread、Project 和协作树，也打开真实目录；Context 和 manifest 准备包含配置、Skill 读取及 write-once 持久化。把整个准入阶段视为无 I/O 的纯校验会隐藏这些边界。

## 决策

### 实现方案

runner 的十类准入拒绝共用一个失败结算出口。`RunAdmissionRejected` 只携带业务 error_type 与文案；输入格式判定、消息读取与 metadata 校验、run type 判定、用户查找、真实 Workdir 授权、chat/resume 解析、心跳启动和 manifest 准备依次执行。拒绝捕获位于外层执行 try 内，结算自身失败仍进入外层取消或基础设施重试策略。

`services/preparation.py` 同时拥有 Context/manifest 生成与清单固化事务。runner 启动心跳后调用准备入口；repository 仅允许有效 lease owner 首次固化 manifest，重试要求生成指纹与持久事实一致。准备失败时复查持久取消，固化完成后再次检查取消，随后才进入图执行。runner 保留实际使用的准备函数导入，性能探针继续包装该调用入口。

准入拒绝在相同的用户加载阶段调用[Run 生命周期结算](2026-10-21-run-terminal-lifecycle.md)。用户尚未加载时保留 available:false；用户已加载时继续读取仅归属于指定 Run 的 checkpoint 用量。没有证据支持“准入会静默丢失当前模型用量”的额外修复；本决定保持现有用量契约。

`scripts/ci_run_service_integration.sh` 的显式测试枚举包含 `test_run_admission.py` 与 `test_agent_run_manifest_and_attempts.py`，复用现有 service integration workflow 执行持久证据。

## 替代方案

- keep：维持十个准入失败结算块，继续重复维护相同生命周期参数。
- narrow：采用内部拒绝原因和单一结算出口，把已有清单事务归回 preparation，保留当前顺序与真实 I/O；当前实现采用此方案。
- replace：纯 gate 或返回全部准备信息的大对象需要提前读取、重排授权或新增维护表面，当前消费者不需要这些机制。
- remove：删除准入检查会绕过持久输入、用户与执行目录边界，不满足现有承诺。

## 后果

runner 保留 lease、取消、重试及执行编排；preparation 拥有 Context/manifest 准备与提交，repository 拥有 fencing 和持久约束。错误类型、文案、拒绝优先序、用户加载时点与 manifest write-once 契约保持一致。实现没有新增准入注册表、参数袋、状态机、配置或公开协议。

## 验证

| 观察边界 | 直接证据 | 结果 |
|---|---|---|
| 准入拒绝原因与顺序 | runner 参数化 unit 同时设置后续错误，断言十类错误的类型、文案和读取/授权/心跳顺序；保留已加载用户的用量及早期 available:false | Passed |
| 拒绝出口自身失败 | unit 注入结算数据库 ConnectionError，断言仍触发外层 lease 释放和基础设施重试 | Passed |
| 准入持久结果与清理 | 新增 7 类进程内真实 runner/PG 用例，回读 Run/Turn failed、原始 error、attempt、租约清除、无输出/manifest 与清理文件 | Passed |
| 准备事务与重试事实 | 新增真实 PG 用例直接调用 production preparation，独立连接回读提交后的 manifest，验证相同指纹复用、不同指纹拒绝及错误 owner fencing | Passed |
| manifest 与停止恢复回归 | 新增 8 项加既有 manifest 7 项、stop recovery 16 项 | Passed：31 项 |
| 完整 unit | host 执行全部非 slow unit | Passed：3050 项 |
| 正式 worker/ARQ 与用户主链路 | 独立 Compose 的 lifecycle、extended lifecycle、cooperation E2E，使用 deterministic replay，并读取状态、等待点、消息与产物 | Passed：30 项，无 skip |
| E2E 收尾 | 独立 PostgreSQL 全库回读 nonterminal_runs、pending_cleanups、cancelling_turns、active_turns | Passed：四项均为 0 |
| 持续阻断接线 | 独立 Review 核对 service integration 脚本显式包含两个持久测试文件 | Inspected |
| 低成本检查 | 工程契约、66 项 verifier unit、全部 5 个变更 Python 文件 Ruff check/format、shell 语法和 diff check | Passed |

隔离 PostgreSQL/Redis 环境中的实际集成命令如下。新增准入测试在当前进程调用真实 runner；正式 ARQ/worker 语义由 Compose E2E 提供。

```bash
uv run --project backend --no-sync --group test pytest \
  backend/test/integration/services/test_run_admission.py \
  backend/test/integration/services/test_agent_run_manifest_and_attempts.py \
  backend/test/integration/services/test_agent_stop_recovery.py -q
```

Compose 已指向独立槽位，测试账号由环境注入：

```bash
docker compose exec -T -e E2E_USERNAME api uv run --no-sync --no-dev pytest \
  test/e2e/test_agent_lifecycle_e2e.py \
  test/e2e/test_agent_lifecycle_extended_e2e.py \
  test/e2e/test_session_cooperation_e2e.py -q --tb=short -ra
```

两个负控均在独立测试子进程中实际执行，磁盘源码与运行服务保持原实现：将共享出口错误类型改为 worker_error，PG 用例因持久错误与 invalid_runtime_payload 不一致失败；移除指纹匹配检查，新准备入口 PG 用例因未拒绝不同指纹失败。独立 Reviewer 复验相同拒绝原因。每轮 pytest exit 1 属于预期负控，未计入正常测试通过数量。

新增 PG 用例隔离外部 VM/通知；真实 Workdir、worker、ARQ、SSE 与运行产物由 E2E 验证。PG 的 fixture rewrite warning 和 E2E 的 pytest cache 权限 warning 不影响断言。远程 CI 未执行，CI 接线由脚本审查、shell 语法和所选测试实测证明；真实外部模型服务未做探针，未验证 provider 漂移。

旧能力不存在：十处重复准入失败结算块，以及 runner 内的 Context/manifest 固化函数定义；runner 的真实调用导入继续由性能探针消费。完整 diff、符号搜索和独立 Review 核对删除范围。

重新引入条件：新增实际消费者拥有不同拒绝承诺或独立事务需求，并具备对应直接证据时重新裁决。
