# 后端测试冗余收敛

状态：implemented
类型：simplification
Owner：docs/develop-guides/testing-guidelines.md

## 问题

[后端测试审计](../../audits/backend-test-audit-2026-10-11.md)识别了同场景重复、无效断言、重复脚手架和过细文件切分。清理需要保留不同入口、层级、权限与持久化边界的独有证据，并维护测试选择器和共享 fixture 的消费者。

## 决策

### 实现方案

测试按业务模块归并同主题文件，用参数矩阵保留各入口、权限、失败与重试分支。知识库 fake、Milvus fake、SQLite UTC 引擎、API Key 签发与清理、Agent Input 数据库 fixture、E2E HTTP/replay helper 由实际消费者共享；跨 unit/integration 的流协议对象由 `backend/test/support/` 拥有。被测生产实现保持原有契约。

`backend/test/integration/conftest.py` 根据整个收集集判断共享服务需求。仅当用例不需要共享 schema/API/沙盒 session fixture，且自行创建和回收资源时，才显式声明 `self_managed_resources`；纯自管批次跳过共享 schema 检查及 API/沙盒清理；任一未标记 integration consumer 使混合批次继续执行这些检查和清理。该标记不承诺独立 PostgreSQL schema。协作状态 HTTP 用例只豁免沙盒清理，保留局部 fixture 以表达这一独有消费关系。marker 注册由 `backend/pyproject.toml` 维护。

`.github/workflows/system-tests.yml` 随归并更新节点；FIFO 批次包含迁出的标题持久化用例，并使用不可达 API/沙盒地址及占位凭据作为外部依赖负控。`scripts/verify_engineering_contracts.py` 与其删除选择器负例继续约束实际 workflow 接线。`backend/test/run_tests.sh` 的 integration/all 按 unit、API、其余 integration 子树、E2E 套件分别执行，保留原选择范围及模块/helper 加载边界。

不同仓储写入口的 lease fencing、model/tool 的 monotonic timing、history/memory 两种读取入口、workspace/viewer 预算传递、查询期间资源删除的 404 映射仍保留独立证据。持久环境 cleanup 的 legacy 标题与 marker 仍有消费者；退役需要先证明历史资源已清理。纯命名或长函数拆分只在消除重复或改善当前消费者定位时执行。

## 替代方案

- 保留现状：证据完整，但重复维护和测试导航成本持续存在。
- 大面积删减测试：文件和用例数量下降，但会丢失分层、入口和负向覆盖。
- 只处理真重复：风险较小，重复脚手架与文件碎片仍然存在。

## 验证

使用独立 Compose 项目及其真实 PostgreSQL、API、worker、Redis、对象存储、向量库和沙盒 provisioner；HTTP 批次显式设置 `TEST_BASE_URL=http://localhost:5050`。E2E 使用确定性 HTTP replay，验证持久化结果、权限拒绝、事件与文件副作用。未调用外部付费模型。下表的 HTTP、PostgreSQL 与 worker 批次属于含反馈能力的原审计基线，主干适配的独立验证另列于表后。

| 验收主张 | 语义 Owner / 直接证据 | 结果 |
|---|---|---|
| 删除与归并保留独有证据 | `backend/test/` 完整 diff、无开发上下文的独立 Reviewer；生产源码 diff 为空 | 审计基线 339 个测试文件归并为 315 个；主干已提交基线 336 个归并为 312 个；查询删除 404、两种历史读取入口、lease fencing 与分层权限证据保留 |
| 单元 fixture、参数与导入有效 | `docker compose exec api uv run --group test pytest test/unit -m "not slow"` | 2661 passed / 60 skipped，7 subtests passed，96.90 秒 |
| HTTP 权限与 helper 保持真实语义 | 真实 HTTP 两批：public knowledge/tools、chat、viewer、bound skill、用户配置；auth、knowledge/evaluation、session resources/items、artifact、upload、feedback、background jobs 等 | 首批 96 passed；次批 106 passed / 1 skipped / 3 failed，修正 Dify fixture 断言、HTTP 地址与测试实例 issuer 后相关 5 项通过；最终 HTTP/helper 与归档补验 25 passed |
| 自管数据库及混合清理保持资源 Owner | 真实 PostgreSQL：Input/FIFO/附件/标题/schema/job/关系/feedback 等；混合批次 lease/manifest/projection/archive/schedule/cooperation/API UID/workdir | 自管批次 123 passed；混合批次 99 passed / 3 failed，过期归档 fixture 与返回契约修正后相关 4 项包含在上述 25 项通过结果中；混合批次保留共享检查与清理 |
| 自管批次不依赖 live API 或 provisioner | workflow 的 FIFO 负控命令，见下方 | 49 passed，API/沙盒地址均不可达且使用非空占位凭据；临时强制恢复共享依赖后，标题用例在 cleanup fixture 中因 ConnectError 变红，源码已恢复 |
| worker 协议与结果仍有效 | lifecycle、extended、bound/shared skill、feedback、permission revocation、draft attachments、input recovery、session config、OpenAI events 的 46 项真实 worker E2E | 首轮 44 passed / 2 failed；合法用户名及公共请求字段修复后，普通用户节点通过；模型失败两参数最终 2 passed。overflow 等待 Input 消费后读取其 owning Turn/Run，最终失败与无重试/摘要断言保留 |
| CI 接线与文档有效 | `python3 scripts/verify_engineering_contracts.py`；`python3 -m unittest scripts.test_verify_engineering_contracts`；相对链接检查；`cd docs && pnpm run build`；`git diff --check` | 工程契约及 64 项自测、相对链接、diff 检查通过；文档最终构建通过（36.62 秒）；按 API/services/E2E 套件边界分别 collect-only 收集 338/303/68 项通过；最终运行脚本 all 经临时转发添加 collect-only 后，真实顺序收集 unit/API/其余 integration/生命周期 E2E 的 2721/338/306/34 项全部通过 |
| 无新静态错误 | Ruff 对 `backend/test` 的 F 检查及完整诊断与 HEAD 对照 | F 检查通过；完整检查的 65 项原有诊断无新增 |

主干交付不引入尚未合入的反馈功能及其测试，只承载测试清理。主干适配候选在相同隔离容器中以独立仓库副本执行 `python -m pytest test/unit -m "not slow"`：2721 passed、7 subtests passed（61.48 秒）；真实 PostgreSQL schema 与 FIFO/附件/标题负控共 60 passed（42.50 秒）。主干适配的工程契约及 64 项自测通过；调试消息投影节点接入 Message audit CI，删除该节点的负例验证 gate 拒绝遗漏，实际两个 HTTP 节点 2 passed（1.22 秒）。候选文档使用已安装的 VitePress 构建通过（7.74 秒）。原审计基线的反馈链路验证属于上表所述审计环境。

实际执行的自管资源负控与 CI 命令相同：

```bash
docker compose exec -T \
  -e TEST_BASE_URL=http://127.0.0.1:1 \
  -e SANDBOX_PROVISIONER_URL=http://127.0.0.1:1 \
  -e SANDBOX_PROVISIONER_TOKEN=fixture-probe-not-used-sandbox-token \
  -e TEST_USERNAME=fixture-probe -e TEST_PASSWORD=fixture-probe \
  api uv run --no-sync --no-dev pytest \
  test/integration/services/test_agent_input_concurrency.py \
  test/integration/services/test_thread_priority_inputs.py \
  test/integration/services/test_input_attachments.py \
  test/integration/services/test_session_title_generation.py -q
```

全量收集按 `pytest test/integration/api --collect-only -q`、`pytest test/integration/services --collect-only -q`、`pytest test/e2e --collect-only -q` 分别执行。原审计基线的单次跨目录默认收集遇到同名 `test_agent_feedback.py` 冲突；全局 importlib 模式还会暴露裸 helper import。主干候选不含这组反馈测试，运行脚本按上述边界分批调用，保持实际 suite/CI 的导入方式。

外部真实模型、可选 parser/provider、独立沙盒镜像探针未执行，因本次环境未配置对应 provider、镜像或凭据；保留其原门控和测试消费者。单测及集成的 skip 按现有可选环境条件执行，不作为通过。pytest cache 权限警告未影响断言与持久化验证。

旧能力不存在：被合并文件、重复测试、死 helper 与旧 selector 不再具有可执行消费者；受影响 workflow selector 随迁移更新并由工程契约负例约束。

重新引入条件：出现现有场景无法证明的独立业务边界或故障，且采用当前目录及共享 fixture。

## 后果

维护同一场景时只修改其 owning 测试或共享 fixture，文件迁移同时维护 CI 节点。参数矩阵保留差异断言；资源清理由创建它的测试拥有，共享清理按混合批次的实际需求执行。独立 Reviewer 对删除替代、协议分支和跨层消费负责；测试数量和完成报告不能代替持久事实。

外部真实模型、可选 parser/provider 与独立沙盒镜像探针的运行需要相应环境。未执行的探针保留原门控与消费者，其覆盖范围按实际结果记录。
