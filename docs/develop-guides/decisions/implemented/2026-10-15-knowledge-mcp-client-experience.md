# 知识库 MCP 的模型调用体验

状态：implemented
类型：feature
Owner：backend/yuxi/api/routers/public_v1/knowledge_mcp.py

## 问题

外部模型经 API Key 调用知识库工具时，需要从协议说明中区分文件名搜索与内容检索、找到原文读取入口，并在调用失败后选择下一步。程序客户端也需要直接消费结果对象，同时保留已有文本客户端的格式。

## 决策

### 实现方案

协议适配器为外部客户端的五个工具发布用途、参数选择、结果串联和分页说明，并在初始化 instructions 中明确检索与核对来源流程。成功响应保留 JSON text，同时提供标准 MCP structuredContent；list_kbs 的数组在结构化字段中包装为 `{"knowledge_bases": [...]}`，其余对象直接发布。输入 Schema、领域结果与资源权限由现有知识库服务负责。当前协议见[知识库 MCP 接入](../../../advanced/knowledge-mcp.md)。

业务错误在适配器映射为固定的可操作说明：400 提示核对参数/知识库支持情况，404 提示重新发现可见资源，500 提示稍后重试。SDK 的输入 Schema 校验仍提供参数级错误；适配器不公开底层异常或输入正文。

## 替代方案

维持仅文本结果与简短说明可以减少协议元数据，但模型使用成本留给每个客户端。独立端点、知识库级凭据、工具组、限流和管理页面涉及新的持久化与授权流程，需要独立需求。写入、问答会话与多库聚合也不属于当前只读检索目标。

API 进程与外部 Key 接线由[内置 MCP 决策](./2026-10-15-knowledge-mcp.md)拥有；内部短期委托与可选启停由[Agent MCP 与可选 Knowledge](./2026-10-23-knowledge-mcp-optional.md)补充，内部与外部调用共享五个只读工具。

## 后果

structuredContent 增加传输体积；原有文本形状保留以支持已有客户端。描述由 MCP adapter 拥有，业务逻辑与输入约束继续复用服务和 Schema。独立端点、授权持久化和写入能力保持单独的需求边界。

## 验证

- `docker compose exec -T api uv run --group test pytest test/unit/routers/test_knowledge_mcp.py -q` 通过。协议结果验证初始化指引、输入约束、文本与结构字段一致、并发身份、错误恢复和诊断脱敏；空业务输入与不可见资源为负向案例。
- `docker compose exec -T api uv run --group test pytest test/integration/api/test_knowledge_mcp.py -q` 通过。测试创建并回收资源，经真实 HTTP 读取 PostgreSQL/MinIO 文档，核对结构字段与文本一致，验证跨用户隔离与 Key 撤销；system-tests workflow 显式运行此文件。
- SDK 与 OpenCode 实测完成知识库发现、检索和来源读取，核对结构结果、非空片段与对应原文。

公网代理和其他 MCP 客户端未验证。真实模型调用与 SDK 探针属于本机实测，稳定回归由 unit 与 HTTP integration 承担。
