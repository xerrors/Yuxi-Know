# 开发分支 CI 与 beta2 版本同步

状态：implemented
类型：process
Owner：.github/workflows/trust.yml

## 问题

质量工作流逐一写死开发分支，新分支需要重复修改触发规则。当前候选仍为 beta1，版本脚本遗漏候选说明与测试拓扑的版本入口。运行链路任务还依赖实际可用的 Cube runner，分支匹配不能证明执行通过。

## 决策

### 实现方案

六个质量工作流的 push 覆盖 main 与 `develop/**`；Ruff 和文档工作流的 PR 目标同样覆盖开发分支，其余 PR 保持现有范围。保留路径过滤、版本 tag、手动入口、job 和权限；文档站仅 main 部署，CLI 仍独立手动发布。开发分支通配规则替代[beta1 准备记录](2026-10-16-080-beta-release-preparation.md)中的单一开发分支规则，手动入口沿用既有决定。

版本脚本同步应用、Compose、锁文件和当前候选说明至 `0.8.0.beta2`，Python 锁文件使用规范化版本。历史发布与验收记录保留原值，CLI 版本独立。当前文档整理随分支交付，无关生产升级提案保持原状。

## 替代方案

- 每次增加一个版本分支：继续重复维护，遗漏检查的风险不变。
- 所有分支无条件运行全部任务：超出开发分支需求，扩大执行开销。
- 跳过缺少 runner 的检查：不能证明运行链路通过，保留排队与明确未验证状态。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 当前与后续开发分支覆盖质量检查 | 写死分支或遗漏 PR 目标 | workflow 事件 | `python3 -m unittest scripts.test_release_workflows`：10 项；7 份 YAML 与原版本比较保留 job、权限及其余事件配置 | 恢复单一分支、缩窄通配符或恢复 PR 仅 main 必须失败 | Passed，本地规则验证 |
| 应用与活动版本入口一致 | 文档或测试拓扑残留 beta1 | 版本脚本、manifest、Compose | `scripts.test_bump_version`：3 项；`uv lock --project backend --check --offline`；manifest 与 11 个镜像默认值回读 | 候选说明和测试镜像夹具覆盖遗漏入口，历史标题保持原值 | Passed |
| 报告绑定实际提交和执行结果 | 用本地测试或排队冒充远端通过 | GitHub Actions runs/jobs | 查询指定分支与 headSha；运行链路尚缺 runner | queued 不计为通过 | Inspected |

本地执行工程契约检查及其单测、版本/工作流/依赖策略单测共 84 项通过；容器后端 unit 为 2902 passed、97 skipped，宿主配置 unit 为 157 passed，补齐容器缺少仓库根文件的范围。前端 lint、完整 unit、typecheck/build 和文档构建通过，124 个本地链接目标与 `git diff --check` 通过。现有依赖弃用、pytest 缓存目录权限和大 bundle 提示不构成对应能力通过的证据。

远端状态读取显示 `develop/0-8-0` 的旧提交 `02cfdec7` 单测、Ruff 与契约通过，运行链路两项排队；仓库 runner 查询为零。最终交付提交的远端结论需要重新读取 Actions，不由本地结果替代。

## 后果

开发分支 CI 增加相应路径变更的运行次数，`develop/**` 包含嵌套分支。规则随工作流所在提交生效，已有其他开发分支仍需合入该配置。运行链路使用托管执行器与本机 Cube，环境与验证由[完整系统测试决定](2026-10-19-hosted-runtime-system-tests.md)维护。

独立服务测试的执行环境与托管 Cube 兼容性验证由[后续决定](2026-10-19-hosted-ci-resource-boundaries.md)维护；完整运行链路的 runner 约束仍由实际 workflow 拥有。
