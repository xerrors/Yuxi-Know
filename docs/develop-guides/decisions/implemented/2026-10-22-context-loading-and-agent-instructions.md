# 收敛上下文加载与文档指令职责

状态：implemented
类型：process
Owner：AGENTS.md

## 问题

根 `AGENTS.md` 要求每个任务预加载 `ARCHITECTURE.md` 和五份 develop-guides，合计约 73KB；对单文件文案或局部 bug 过重。根文件的“提交前至少运行”又要求文档改动运行后端 unit，与改动面证据表冲突。`backend/AGENTS.md` 把 ruff 描述为从仓库根目录运行，但命令实际切换到 `backend`，在同一 shell 连续执行时 cwd 会保留并导致后续命令失败。`docs/AGENTS.md` 重复了 `documentation-guidelines.md` 已拥有的写作规则，形成双 Owner。

## 决策

### 实现方案

- 根 `AGENTS.md` 改为按任务范围加载：局部改动只读根指令和相关源码；跨模块、状态/权限/持久化/外部副作用或架构选择才读 `ARCHITECTURE.md`，非平凡变更再读 Spec Loop 和工程信任系统，涉及测试时读测试规范；提交或创建 PR 前读贡献指南。
- “至少运行”只约束代码变更；文档和导航改动按下表执行相对链接检查和 docs build。
- `backend/AGENTS.md` 的 ruff 命令改为子 shell 中进入 `backend` 执行，保持与 `ruff.yml` 的工作目录一致，并可从仓库根目录连续运行。
- `docs/AGENTS.md` 只保留进入 `docs/` 时必须执行的约束；语言、结构、示例、安全和决策记录细节由 `documentation-guidelines.md` 拥有。

## 替代方案

- 保留每次任务预加载全部文档：小任务承担约 73KB 固定成本，且与实际阅读范围不符。
- 把文档规范继续留在 `docs/AGENTS.md`：形成两个可独立编辑的 Owner。
- 用绝对路径或 `uv run --project backend` 重写 ruff 命令：与 CI 的 backend 工作目录不完全等价，且需要额外验证。

## 后果

小任务不再预加载约 73KB 文档；跨模块变更仍按 Spec Loop、工程信任和测试规范执行。文档和导航改动不再被后端 unit 阻塞。`docs/AGENTS.md` 与 `documentation-guidelines.md` 的职责边界更清楚。

## 验证

- `python3 scripts/verify_engineering_contracts.py`
- `python3 -m unittest scripts.test_verify_engineering_contracts`
- `git diff --check`
