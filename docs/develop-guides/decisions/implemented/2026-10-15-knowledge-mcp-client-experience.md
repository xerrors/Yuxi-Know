# 知识库 MCP 的模型调用体验

状态：implemented
类型：feature
Owner：backend/yuxi/api/routers/public_v1/knowledge_mcp.py

## 问题

外部模型经 API Key 调用知识库工具时，需要从协议说明中区分文件名搜索与内容检索、找到原文读取入口，并在调用失败后选择下一步。程序客户端也需要直接消费结果对象，同时保留已有文本客户端的格式。

## 决策

### 实现方案

协议适配器为五个工具发布用途、参数选择、结果串联和分页说明，并在初始化 instructions 中明确检索与核对来源流程。成功响应保留 JSON text，同时提供标准 MCP structuredContent；list_kbs 的数组在结构化字段中包装为 `{"knowledge_bases": [...]}`，其余对象直接发布。输入 Schema、领域结果与资源权限由现有知识库服务负责。当前协议见[知识库 MCP 接入](../../../advanced/knowledge-mcp.md)。

业务错误在适配器映射为固定的可操作说明：400 提示核对参数/知识库支持情况，404 提示重新发现可见资源，500 提示稍后重试。SDK 的输入 Schema 校验仍提供参数级错误；适配器不公开底层异常或输入正文。

## 替代方案

维持仅文本结果与简短说明可以减少协议元数据，但模型使用成本留给每个客户端。复制 WeKnora 的独立端点、知识库级凭据、工具组、限流和管理页面涉及新的持久化与授权流程，超出小范围补齐。写入、问答会话与多库聚合也不属于当前只读检索目标。

固定版本源码与能力差距见 [WeKnora MCP 对标](../../weknora-mcp-comparison.md)。API 进程与权限接线由[内置 MCP 决策](./2026-10-15-knowledge-mcp.md)拥有。

## 后果

structuredContent 增加传输体积；原有文本形状保留以支持已有客户端。描述由 MCP adapter 拥有，业务逻辑与输入约束继续复用服务和 Schema。独立端点、授权持久化和写入能力保持单独的需求边界。

## 验证

- `docker compose exec -T api uv run --group test pytest test/unit/routers/test_knowledge_mcp.py -q`：24 passed。协议结果断言初始化指引、工具输入、文本与结构字段一致、并发身份、错误恢复和诊断脱敏；空业务输入与不可见资源为负向案例。
- `docker compose exec -T api uv run --group test pytest test/integration/api/test_knowledge_mcp.py -q`：2 passed。自动创建和回收资源，真实 HTTP 读取 PostgreSQL/MinIO 文档，核对列表、搜索、原文和定位的结构字段与文本一致，验证跨用户与撤销 Key；已有 system-tests workflow 显式运行此文件。
- `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow'`：2622 passed、59 skipped、7 subtests passed。命令在现有开发 Compose 执行，结果反映含其他并行开发改动的实际部署树；本轮仅同步无并发变化的 MCP adapter 与两份测试。
- SDK 1.29.1 在 `/api/mcp` 调用五个工具，回读证明结构结果与文本一致，真实检索为 8 个片段、原文 11 行、关键词命中 1 行，不可见资源返回恢复指引。初次探针未固定 SDK 版本时解析到 2.x，因探针依赖 httpx 而该环境只含 httpx2 未运行成功；固定为后端锁定的 1.29.1 后通过。
- `opencode mcp list` 为 connected；`opencode run --model siliconflow-cn/deepseek-ai/DeepSeek-V4-Flash --auto --format json` 的实际工具结果回读证明三个工具 completed、8 个非空片段、最高分来源的 11 行原文。
- `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`（64 tests）、`uvx ruff check` 与 `uvx ruff format --check`（三份改动 Python）、`cd docs && pnpm run build`、`git diff --check` 通过。

WeKnora 仅作固定源码研究，未部署运行；公网代理和其他 MCP 客户端未验证。真实模型调用与 SDK 探针属于本机实测，稳定回归由 unit 与 HTTP integration 承担。
