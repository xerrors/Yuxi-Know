# Agent 通过 MCP 访问可选 Knowledge

状态：implemented
类型：architecture
Owner：backend/yuxi/api/routers/public_v1/knowledge_mcp.py

## 问题

平台需要保留知识库代码与数据，同时允许部署不启动 Milvus、etcd 和 Neo4j。Agent 的本地知识库调用与启动连接使该部署方式无法隔离故障。调用边界改变后，用户当前权限和会话选择范围必须保持，停启不能清空选择或丢弃待执行任务。

## 决策

### 实现方案

Agent 保留五个知识查询工具的名称、参数和结果形状，数据读取全部经平台 Knowledge MCP HTTP 地址；选择器和来源标注也使用该边界。可信 runtime 按运行用户 uid 和原会话选择签发五分钟委托 JWT，每个 HTTP 请求重新签发，不落库。固定的同实例 issuer、独立 audience/purpose 和短有效期隔离登录凭据；MCP 每次请求复核当前账号状态，每次工具执行重新读取知识库权限并与签名选择取交集。显式空列表保持空范围，Knowledge 不借用 Public end_user 所属管理员的权限。

外部 API Key 与内部委托使用相同五个只读工具。`list_kbs` 可附带文档能力，供资源选择器和来源标注使用。不提供 Agent 原件下载工具，原有管理文件下载接口保留。内部 HTTP 客户端不跟随重定向，不读取环境代理，避免委托凭据离开平台连接。

`YUXI_KNOWLEDGE_ENABLED` 默认开启。关闭时，API 集中装配层不初始化知识库执行器、不注册 Knowledge MCP 及管理路由；worker 不领取或补发知识任务，保留 PostgreSQL pending 意图和投影清理意图。Compose 关闭覆盖把 Milvus、etcd 和 Neo4j 副本数设为零，不删除持久挂载；原代码、Schema、配置和数据保留。普通工具和 Skill 继续装配，知识工具返回安全的 MCP 不可用错误，不存在本地调用 fallback。内部故障使用保留标识 `platform:knowledge`，不覆盖用户同名外部 MCP 的状态。

启用 Knowledge 时，API 与 worker 在普通安全初始化之前校验显式共享的 `JWT_SECRET_KEY` 和 `YUXI_INSTANCE_ID`。worker 在任何恢复、补发和消费之前初始化已有知识库执行器，并建立真实 Neo4j 会话。后端未就绪使进程启动失败，由现有 Compose 重启策略恢复，pending 任务不被提前领取；worker 关闭释放共享图连接。关闭模式跳过这些 Knowledge 前提。

身份签验由 identity security/service 拥有；权限由 Knowledge access/service 拥有；Agent MCP 客户端和工具适配拥有传输与运行态错误；bootstrap、worker 与 Compose 拥有启动顺序和启停。本决定部分取代[内置知识库 MCP](./2026-10-15-knowledge-mcp.md)的仅 API Key 与始终挂载条款，并对[资源选择](./2026-09-27-explicit-resource-selection.md)增加知识库在 MCP 执行交集的例外。外部客户端说明与错误指导继续由[模型调用体验](./2026-10-15-knowledge-mcp-client-experience.md)拥有。

## 替代方案

- 只调整后端连接可以降低部署成本，但保留 Agent 对 Knowledge 实现的直接依赖，无法满足统一调用边界。
- 自动生成长期用户 Key 增加持久化、撤销和轮换，不天然表达每次会话的选择范围。
- 通用 OAuth 或独立 Knowledge 服务增加授权与部署表面，当前同平台调用没有相应 consumer。
- 只依赖 Compose 启动顺序无法覆盖直接宿主进程；worker 启动阶段复用真实连接检查同时保护队列补发与消费，不新增通用重试机制。

## 后果

平台支持同一项目的完整部署与关闭 Knowledge 两种启动方式，不支持热切换，不拆数据库或删除连接器。显式关闭与后端故障保持不同状态；启用后的故障仍如实失败，不自动重试已经失败的领域任务。

MCP 每次调用增加握手、认证和网络往返，先不缓存身份或连接。引用读取仅在 Turn 含知识检索工具结果时经 MCP 解析可见范围，普通回答不产生知识库会话。启用 Knowledge 的 worker 显式依赖图谱连接，裁剪的测试拓扑也需启动 Neo4j。签名密钥仍是部署级信任根，不能注入 Agent 沙盒、模型上下文或日志。

## 验证

- Passed：内部签验、实时撤权、会话选择与 end_user 隔离的 unit 和真实 HTTP；真实 worker 执行五个工具、生成引用，知识失败后继续回答并保留选择。
- Passed：引用加载单测区分网页、空检索与知识检索，网页和空检索不发起 MCP 会话，知识来源仍重新请求 MCP 可见范围并保留文档能力。
- Passed：隔离 Compose 完成开启、关闭、重新开启。关闭时 Milvus、etcd、Neo4j 均未运行，管理与 MCP 接口返回 404，待解析任务保持 pending；重新开启后同一任务成功，原件字节与 MCP 正文一致。
- Passed：分阶段真实服务探针在三个阶段通过同一普通用户与同一显式选择会话执行 worker，回读 PostgreSQL 中显式选择、空列表和 `all` 三份会话配置、两份知识库授权及四份对象内容。开启和恢复时，三种选择分别通过 HTTP MCP 验证访问范围；关闭时工具失败后继续完成回答，恢复后猜测无权资源仍被拒绝。探针只重放外部模型协议，API、worker、MCP、权限与持久化均使用真实服务。
- Passed：启动负向案例验证缺少共享密钥或实例标识时不连接数据库、不生成随机身份；Milvus/Neo4j 未就绪时不补发任务；关闭时不连接知识后端；内部状态不影响同名外部 MCP。

具体最终批次、负向案例与未验证范围由[工具边界收敛决策](./2026-10-23-knowledge-mcp-simplification.md)记录。该决定取消原件下载工具，保留现有管理下载接口和数据。
