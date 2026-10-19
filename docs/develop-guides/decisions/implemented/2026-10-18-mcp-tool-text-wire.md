# MCP 工具结果与真实模型的文本协议

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/models/chat.py

## 问题

个人考勤已经返回真实工具结果，但真实供应商在下一次 Chat Completions 请求拒绝数组形式的 tool.content。现有固定模型 E2E 接受数组，无法证明真实模型能完成工具续答。

## 决策

### 实现方案

在 ChatCompletionsAdapter 的发送边界将纯文本工具块列表按顺序转为换行分隔的字符串。只改 wire 副本，保留原始 ToolMessage、artifact、工具审计与 checkpoint；用户多模态内容和其他供应商适配器维持既有协议。既有图片桥接仍由模型输入中间件拥有。

## 替代方案

- MCP executor 提前扁平化结果：会改变持久结果与多模态语义，且遗漏其他返回文本块的工具。
- 按供应商名称增加开关：当前 consumer 需要统一的纯文本工具字符串协议，会增加配置与维护分支。

## 后果

Chat Completions 请求中的纯文本工具数组转换为有序换行文本；原始 checkpoint、artifact 和审计仍保留结构化工具结果。其他角色的多模态消息与非文本工具块维持既有处理。真实供应商的最终续答需要独立验收，固定模型只证明其实际覆盖的协议和业务链路。

## 验证

- 独立 HTTP oracle 明确拒绝数组 tool.content：旧代码的 9 个新用例均失败，其中 8 个收到 400，另一个暴露空数组未转换。修复后，9 项新测试及既有无效调用/图片桥接集合共 33 项通过，覆盖同步、异步、流式、非流式与推理模式，并验证原始消息与 artifact 不变。
- 主站真实 Chromium 使用默认可信 HTTPS 完成三种角色的企业登录，在默认智能助手页面选择实际供应商模型 `opencode-go:deepseek-v4.1-flash`，从输入框提交日期查询，实际 MCP 查询及模型最终答复均成功。另使用用户原话“查一下我的考勤”完成一个真实浏览器案例；共 4 个真实模型案例，未使用 replay 或拦截替换模型响应。
- 每个案例分别回读 PostgreSQL 的实际模型 spec、调用 uid、成功 tool_audit、本人考勤结果、Turn.result_run_id 和对应持久最终消息；页面呈现最终答复，三角色结果互斥。截图和运行标识仅保存在私有运维目录，不进入仓库。
- 固定模型的 MCP E2E 只证明授权、真实资源调用和 worker 持久链路，无法代替真实供应商的消息协议验证。真实模型案例闭合此前遗漏的工具续答兼容性。


实际检查命令：

- `docker compose exec -T api uv run --no-sync --group test pytest test/unit -m 'not slow' -q --tb=short -o cache_dir=/tmp/mcp-pytest`：2867 passed，97 skipped。
- `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`：工程契约与 66 项检查测试通过。
- `pnpm --dir docs run build`、相关 Ruff 与 `git diff --check`：通过。

独立 Reviewer 已审查发送边界、测试与图片桥接，未发现剩余代码阻断。
