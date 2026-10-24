# 摘要中间件 tool_result_offload_token_limit 的 None 语义定为关闭 offload

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/runtime/middlewares/summary.py

## 问题

`tool_result_offload_token_limit=None` 的旧语义是"所有工具结果都 offload 且预览保留全文"：改写每条工具消息、写文件副本，但不减少任何进入模型的内容，纯增开销；且该参数没有任何取值能真正关闭 offload。惯例上 None 表示关闭该能力，旧语义构成签名陷阱。翻转前已核实：唯一生产入口 `create_summary_middleware_from_context` 读取的 `summary_tool_result_token_limit` 是带默认值 300 的 int 字段，不存在 None 来源，旧 None 语义没有生产 consumer。

## 决策

`_should_offload_tool_message` 把 None 定义为关闭工具结果 offload（消息保持原样）；非正值表示全部 offload 且预览为空；正值为触发阈值。语义记录在函数 docstring 与 `create_summary_middleware` 说明中。

### 实现方案

仅修改 `_should_offload_tool_message` 的 None 分支与工厂 docstring；`_build_tool_result_preview` 的 None 分支保留为该路径下的不可达兜底。单测新增 None 关闭 offload 的专项断言，原"None 全文预览"场景改写为"offload 关闭时原文只进入摘要输入、不进入模型视图"。

## 替代方案

- 保留旧 None 语义并加注释：陷阱仍在，签名继续邀请调用方传 None 触发最激进行为。
- 移除 None 使参数必填 int：破坏工厂与既有测试签名，收益仅剩语义提示。

## 后果

显式传 None 的调用方从"全部 offload"变为"完全不 offload"；当前无生产调用方受影响。0 与正值的语义不变。

## 验证

`test/unit/middlewares/test_summary_middleware.py` 新增 `test_compact_messages_without_tool_result_limit_keeps_tool_results`（None 不写文件、内容原样）；offload 场景参数化补 None 分支断言。全量 unit 保持通过。

旧能力不存在：`_should_offload_tool_message` 对 None 返回 False，None 不触发任何 backend 写入；"None 即 offload 全部"的分支经负向搜索不存在。

重新引入条件：若未来需要"offload 全部且预览保留全文"的行为，必须以显式参数或独立模式命名该语义，不得复用 None。
