# 质量检查支持指定分支手动补跑

状态：implemented
类型：testing
Owner：.github/workflows/frontend.yml

## 问题

Fork 的 Actions 恢复后，停用期间的 push 没有检查记录。前端、后端单测和 Ruff 工作流只有 push/PR 入口，无法对当前分支直接补跑。

## 决策

### 实现方案

为 frontend.yml、test.yml 和 ruff.yml 增加 workflow_dispatch，复用各自已有 job、权限、依赖版本与检查命令。分支和 tag 自动触发、路径过滤及发布边界继续由原工作流拥有；手动运行使用指定 ref 对应的提交。

## 替代方案

为补跑创建 PR 会引入额外交付对象。修改无关业务文件触发 push 会污染变更范围。手动入口直接服务当前分支的缺失检查。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 既有质量检查增加手动事件且保留原门禁 | 工作流事件与 job 装配 | frontend / test / ruff 工作流 | YAML 结构与 HEAD 对比仅多出 workflow_dispatch；工程契约与发布边界 76 项单测通过 | 既有测试拒绝缺失版本触发或改变开发分支；job、权限和其余事件逐项一致 | Passed |

执行 `python3 scripts/verify_engineering_contracts.py` 和 `python3 -m unittest scripts.test_verify_engineering_contracts scripts.test_release_workflows`。三个工作流的 YAML 解析结果在移除新增事件后与原提交完全相同。远端运行的提交归属与最终结果由 GitHub Actions 的 headSha、job 和日志拥有，静态检查不代替远端执行。

## 后果

手动运行仍依赖 GitHub Actions 可用及执行环境就绪。运行链路的 Cube runner、变量和密钥由既有 system-tests.yml 使用，不由新增入口提供。
