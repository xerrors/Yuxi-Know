# develop 分支的质量检查

状态：implemented
类型：testing
Owner：.github/workflows/system-tests.yml

## 问题

`develop/0-8-0` 交付需要同一提交的 GitHub 检查证据。既有质量 workflow 的 push 仅接受 main，develop 推送只自动构建文档，不能证明后端、前端和真实运行链路。

## 决策

### 实现方案

Ruff、后端 unit、前端质量、工程信任、依赖审计和 Runtime System Tests 的 push 分支列表匹配 `develop/0-8-0`。复用原有 job、依赖、命令、权限、路径过滤及失败行为。结果由 GitHub run 的 head SHA 与 conclusion 拥有，检查失败仍产生拒绝后果。

## 替代方案

- 只增加手动入口：受 GitHub 默认分支的 workflow 前置条件限制，不能仅靠 develop 推送视为可用。
- 制造 PR 或复制检查 job：新增交付对象或命令副本，固定开发分支触发满足当前需求。
- 让所有分支 push 都运行：增加无当前验收需求的运行成本。

## 后果

符合既有路径过滤的 develop 推送运行同等检查并产生 Actions 成本。main/PR 的检查内容和保护规则保持原样，开发分支的完成报告需要对应 SHA 的实际检查结果。

## 验证

- Inspected：workflow 只扩大 push 到当前开发分支，既有 jobs、权限和路径过滤不变。
- Passed：工程契约与自测试验证 YAML 装配和 Owner 记录；远程运行证据以对应提交的 GitHub 检查为准。
