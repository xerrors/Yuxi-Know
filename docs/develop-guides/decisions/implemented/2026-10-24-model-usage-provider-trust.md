# SiliconFlow 用量数据按 provider 域声明为不可信并从聚合中剔除

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/models/providers/builtin.py

## 问题

SiliconFlow（`siliconflow-cn`、`siliconflow`）返回的 usage_metadata 与真实账单存在偏差，直接累计会污染 Run/Thread 用量聚合与前端展示。该分类此前以 `TOKEN_USAGE_PROVIDER_BLACKLIST` 常量硬编码在观测中间件（`token_usage.py`）内，而 `siliconflow-cn` 同时是系统默认 provider——默认部署下大部分主模型调用的真实用量被剔除，但剔除原因与语义 Owner 都不在 provider 域，观测中间件承担了 provider 数据质量的判断。

## 决策

分类常量迁至 `yuxi/modules/models/providers/builtin.py` 的 `USAGE_UNTRUSTED_PROVIDER_IDS`，与 provider 目录同处维护并说明移除条件；`token_usage.py` 只消费该分类。观测语义不变：不可信 provider 的模型调用计入 `model_call_count` 与 `usage_unavailable_call_count`，不累计 usage 细分，历史 checkpoint 中的既有分桶在读取时继续剔除。

### 实现方案

`builtin.py` 持有分类常量与注释；`token_usage.py` 删除本地常量，`before_agent`、`_build_snapshot` 与历史桶清理改用导入的 `USAGE_UNTRUSTED_PROVIDER_IDS`，辅助函数更名为 `_without_untrusted_providers` 以匹配语义。分类不进入 provider 数据模型，DB 中管理员自建 provider 默认按可信处理。

## 替代方案

- provider 定义加结构化字段（如 `usage_trusted` 列）：需要数据迁移与 cache/元数据链路传递，当前只有 builtin 两家需要分类，成本不匹配。
- 在适配层修正 SiliconFlow 的用量口径：是对齐真实账单的正解，修复后应直接删除该分类而不是保留规避逻辑；上游口径未核实前不行动。
- 保留中间件内常量：Owner 错位，provider 数据质量问题应由 provider 域拥有。

## 后果

新增自定义 provider 默认按可信处理；其他 provider 出现同类问题时在 `USAGE_UNTRUSTED_PROVIDER_IDS` 登记即可。管理员自建 provider 无法被标记为不可信——若出现该需求，应先落地 provider 级结构化字段，而不是回迁观测层常量。

## 验证

`test/unit/middlewares/test_token_usage_middleware.py` 既有断言（跳过 siliconflow 用量、清理历史不可信桶）语义不变、保持通过；全仓不再存在 `TOKEN_USAGE_PROVIDER_BLACKLIST` 引用。完整命令与结果随交付记录。

旧能力不存在：`token_usage.py` 内不再定义 provider 信任分类常量，`_without_blacklisted_providers` 名称与 `TOKEN_USAGE_PROVIDER_BLACKLIST` 标识符经全仓负向搜索确认不存在。

重新引入条件：仅当 provider 级结构化信任字段（含数据迁移与 cache 传递）落地并取代该常量时，才允许把分类从 `builtin.py` 迁出；上游用量口径修复后应直接删除分类而不是迁回观测层。
