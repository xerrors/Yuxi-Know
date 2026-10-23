# 收敛知识库 MCP 工具与调用边界

状态：implemented
类型：simplification
Owner：backend/yuxi/api/routers/public_v1/knowledge_mcp.py

## 问题

Agent 与 Knowledge 的 MCP 边界需要保留现有五个查询工具、实时权限和会话选择语义。用户明确不需要 `download_kb_file`；其内部专用协议、二进制传输和沙盒写入增加了无当前需求的维护面。

## 决策

### 实现方案

删除下载工具的注册、Skill 依赖、MCP Schema/执行、Base64 传输与 Agent 沙盒写入适配；现有知识库管理文件下载接口及底层存储用例保持。Agent 和外部客户端使用相同五个只读 MCP 工具，继续以外部 Key 或内部短期委托解析实时可见范围。权限、异常、取消和异步执行边界保持，不引入新依赖、缓存或兼容路径。

## 替代方案

- 保留下载工具：无本任务 consumer，继续维护单独授权、载荷和沙盒边界。
- 保留兼容空壳：仍向模型或工具目录宣告已取消能力，增加额外失败路径。
- 通用化 MCP 客户端或引入授权缓存：当前固定五工具调用没有足够收益，且增加撤权和并发语义风险。

## 后果

内部与外部 MCP 共享五个查询工具，取消下载专用的授权分支、载荷编解码和沙盒文件投影；Knowledge 不承担 Agent 文件副作用。可见范围统一交给现有 access service，discovery 在一次响应内复用开关值，纯知识用例测试直接传入可见集合。

短期委托逐请求签发、实时身份复核、HTTP/MCP 会话和异步清理各有当前 Owner，保留这些职责与失败语义；不引入连接或授权缓存。每次 MCP 握手的开销继续存在，尚无负载证据支持改变连接生命周期或事务边界。

下载能力按明确需求删除；既有用户自定义 Skill 若引用旧工具，需要自行移除该依赖，不重写持久配置或历史消息。原有管理下载接口、原件、知识库元数据和连接器保留。

## 验证

- Passed：相关 unit 162 项，覆盖五工具目录、内置 Skill 依赖、文档窗口、分页和协议错误；独立 Reviewer 另运行委托签验、客户端协议、MCP 路由 unit 40 项。
- Passed：真实 HTTP 18 项，覆盖内容回读、外部 Key 和内部委托目录均只有五工具、猜测旧工具名返回 unknown-tool、空选择、同 Token 撤权、失效账号、end_user 权限和登录凭据隔离。对应 `test_knowledge_mcp.py`、`test_knowledge_mcp_delegation.py` 与 `test_knowledge_access_resolution.py`。
- Passed：恢复完整部署后，`test_knowledge_mcp_agent.py`、`test_milvus_text_retrieval_e2e.py` 与工具结果一致性 E2E 共 5 项；经真实 API/worker/MCP/Milvus/MinIO/Neo4j 回读工具结果、索引、正文、引用、投影清理与 PostgreSQL 审计。共享槽内 HTTP 和 E2E 串行运行，避免全局测试资源清理相互干扰。
- Passed：隔离 Compose 实际停用三个知识后端，MCP 与管理接口 404，待解析任务持续 pending；同一显式选择会话在关闭时收到工具错误并完成回答。恢复后同一任务 success、原件字节与 MCP 正文一致，同一会话恢复查询；三种选择与用户授权的跨阶段回读见[可选部署决定](./2026-10-23-knowledge-mcp-optional.md)。
- Passed：`docker compose exec -T api uv run --no-sync --group test pytest test/unit -m "not slow" -q`：3191 passed、117 skipped；宿主部署与引用单测 54 项通过。宿主批次补充仓库根部署配置断言，不把所有容器 skip 解释为已覆盖。
- Passed：工程信任检查、检查器与 CI 资源边界测试 77 项，源 Ruff check/format/import 三项、文档相对链接与 build、`git diff HEAD --check`。

旧能力不存在：源码不再定义或注册 `download_kb_file`，Skill 不依赖它，委托和 API Key 均不能调用；历史文档与拒绝测试可保留名称。

重新引入条件：出现明确的 Agent 原件下载需求，并重新审查文件传输、授权和 owning filesystem 边界。

未验证范围：真实外部模型引用探针缺少 `REFERENCE_PROBE_MODEL`；公网 HTTPS、跨机器和第三方客户端未验证。未执行负载测试，不宣称额外网络往返的吞吐表现。
