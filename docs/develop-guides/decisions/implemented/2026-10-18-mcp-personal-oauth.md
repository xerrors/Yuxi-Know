# MCP 个人授权与运行边界

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/extensions/mcp/service.py

## 问题

共享 MCP headers 无法表达个人资源授权；Agent、Skills 与 service 重复保存连接提示、工具开关和目录缓存，又增加跨用户隔离与 API/worker 失效一致性的维护成本。以模型工具可见性代替实际调用授权，还会让已装配工具绕过断开或配置撤销。

## 决策

### 实现方案

MCP service 统一解析全局服务开关与本人连接，按可信运行 uid 返回可用服务和工具；repository 负责持久查询，复用 session 时刷新已加载 ORM 对象。授权配置归 oauth_config，协议归 oauth_protocol，个人连接事务归 oauth_service，个人工具与出站适配归 oauth_runtime。HTTP 路由只负责认证上下文、协议与响应。操作说明归 [MCP 集成](../../../agents/mcp-integration.md)，当前机制归 [MCP 机制](../../../mechanisms/mcp.md)。

个人连接由 PostgreSQL 唯一约束与行锁隔离，授权发起、回调和当前登录用户确认均核对浏览器、state、配置修订及连接世代。配置修订改变时，同一事务推进世代并清空凭据，配置改回原值也不能恢复旧授权；断开同样使旧事务失效。刷新在连接锁内轮换令牌，远端返回后复查策略再保存；晚到的 401 只撤销仍与被拒值相同的凭据。

Agent、Skills、协作与定时执行沿已确定的执行用户调用 service。Authorization 统一实施配置选择、Skill 激活与嵌套依赖门控，在模型和工具执行边界读取当前策略；Skills 只负责提示内容、激活及实际激活依赖的工具绑定。Context 持有本 Run 装配所需的工具对象及来源，不保存禁用工具投影。未连接服务从装配结果排除，普通聊天继续；连接状态与操作入口由扩展页面提供。Context 的故障提示与网络异常隔离由 [MCP 故障隔离决定](./2026-10-20-mcp-runtime-degradation.md)补充。

共享 headers 与个人 OAuth 每个实际使用服务每 Run 成功发现一次目录，合法空目录同样复用；新 Run 使用独立 Context 重新发现。管理端普通 GET 直接读取远端工具。删除进程缓存、配置哈希、失效函数、刷新开关、统计缓存和重复刷新接口；API 与 worker 无需维护目录同步。Authorization 在实际调用前检查执行用户与当前策略；共享 HTTP 适配器复查服务模式、加载时连接字段和工具开关，个人 HTTP 适配器按当前用户及配置修订取得有效 token。个人 token 不缓存在工具对象里。

凭据只保存在服务端加密列中；OAuth 回调 query 不进入访问日志，异常日志保留堆栈但关闭局部变量展开，避免 adapter 与 ExceptionGroup 携带的 token、code 或 secret 被诊断输出。生产 Nginx 复用 OIDC 的安全日志格式，为 MCP API 回调与 `/extensions` 返回页记录固定路径并设置 `no-store`、`no-referrer`，关闭会携带原始请求的该入口 error log；普通请求的 Referer 同样屏蔽这些授权来源。

平台 OIDC 登录与 MCP 资源授权分离，资源账号不要求与平台企业员工一致；拒绝已删除的企业身份策略字段。界面统一使用 Plug，删除自定义图标、标签和 GitHub/Notion 表单预设，保留 DeepWiki 与通用授权配置。所有用户可查看简介并管理本人连接，仅超级管理员管理全局服务；键盘入口遵循同一权限边界。

通用凭据密钥与固定回调由 [部署配置决定](./2026-10-19-common-credential-encryption.md)拥有，认证中心和考勤示例由 [独立认证部署](./2026-10-18-extract-yuxi-auth.md)拥有，数据库结构和 UID 容量由 [Schema 基线](./2026-10-19-schema-baseline-one.md)拥有。工具结果进入真实模型的文本协议见 [模型发送边界](./2026-10-18-mcp-tool-text-wire.md)。

## 替代方案

共享管理员 token 或按用户复制服务器无法同时满足统一配置与本人隔离；转发平台登录 token 会混淆资源与 scope。按供应商增加连接器类层次、专用表单或企业身份校验没有当前协议需求。

逐层清理 adapter 与 ExceptionGroup 的异常载荷难以覆盖所有凭据路径；统一关闭堆栈的局部变量展开，保留异常类型与调用位置，减少日志泄漏面。

仅在装配时授权、隐藏模型 schema 或清理目录缓存，均不能撤销已持有的工具对象；保留双重门控和连接通知投影继续维护重复事实。选择 service 拥有可用性，Authorization 拥有执行门控，HTTP 适配器守住真实出站。

进程共享目录只省掉下一 Run 的首次发现，却需要跨进程失效；每轮重新发现又增加重复网络开销。每 Run 装配一次保留实际收益，目录生命周期由现有 Context 拥有，无需 TTL、目录版本或广播机制。

## 后果

本地 connected 状态不保证远端 token 一直有效，刷新或调用被拒后需要重连；本地断开不等于供应商侧撤销，也不能收回已送达远端的请求。既有工具对象的后续请求仍以当前持久权限为准，个人授权不会退回管理员凭据。

工具 schema 在新 Run 更新；短小高频 Run 不再获得跨运行目录命中收益。当前 SDK 每次成功调用后还会读取目录校验结果，协议回放中三轮模型、两次工具调用对应一次应用发现与两次 SDK 校验，共三次 tools/list，进程缓存无法省去后两次。没有生产延迟或吞吐测量，不宣称性能提升。

聊天不注入 MCP 连接指引或发送逐服务通知；历史提示行为的验收不构成当前承诺。GitHub 的真实授权暂缓，Notion 最终停止接入，供应商适配限制由 [协议核对](../../audits/mcp-oauth-compatibility-2026-10-18.md)维护。

## 验证

以下结果来自对应实现阶段已执行的命令；文档合并不代表重新执行业务测试。

| 证据 | 覆盖与结果 |
| --- | --- |
| `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q` | 通用凭据配置完成后的完整集合：2902 passed、97 skipped；最终相关配置 unit 复验 43 passed |
| `docker compose exec -T api uv run --group test pytest test/integration/services/test_mcp_oauth.py test/integration/api/test_mcp_router.py test/integration/services/test_runtime_authorization_boundaries.py test/integration/services/test_optional_dependency_failures.py -q` | 目录与刷新入口清理阶段：80 passed；真实 HTTP/PostgreSQL 覆盖本人隔离、配置往返撤销、旧共享对象、并发刷新、断开及当前 GET 目录与开关 |
| `docker compose exec -T api uv run --group test pytest test/integration/services/test_mcp_oauth.py -q` | 通用凭据配置完成后：43 passed，固定回调经过独立注册端点与 token 端点核对 |
| 真实 LangGraph、生产 middleware factory 与 HTTP 协议回放 | 共享/个人 × 直接/Skill 四组合，每组两次 Run、各三轮模型与两次调用；每 Run 应用发现一次，第二 Run 取得新 schema；空目录复用、动态开关、断开及双用户目录隔离通过 |
| 负向案例 | 停用、断开及禁用工具在持有旧 ORM 对象时仍使用最新策略；旧共享对象不能在切换个人 OAuth 后复活；嵌套依赖不可用时本地 Skill 不能产生文件副作用；未知协议错误继续抛出 |
| 前端检查 | 刷新入口清理阶段 lint 与 726 项 unit 通过；三角色、窄屏、浅深色、私有 Agent 和键盘入口的浏览器证据属于早期部署，适用边界见 [历史验收](../../audits/mcp-main-e2e-2026-10-18.md) |
| `python3 scripts/verify_oidc_proxy.py` | 真实 Nginx 覆盖 OIDC/MCP 归一化回调路径、SPA 返回正文、上游 502、响应头及普通请求 Referer；回读实际日志拒绝授权码、state 和一次性结果标记。恢复旧配置时在 MCP 回调缺少安全响应头处失败，原始 error log 同时包含假参数 |

早期真实授权服务器、worker、协作/定时身份与实际模型考勤验收保存在上述历史记录；删除连接提示、共享目录缓存及调整通用配置后，没有重新执行外部供应商浏览器或企业 worker E2E，不将早期结果作为最终源码的全链路证明。当前实现的授权与目录行为由真实 HTTP/PostgreSQL 及 LangGraph 测试证明。

旧能力不存在：Agent/Skills 的连接通知状态、Context 工具开关投影、重复本地工具门控、进程目录与统计缓存、失效及刷新专用接口、自定义展示字段、供应商表单预设和企业身份一致性策略均已移除。

重新引入条件：生产发现延迟、明确聊天通知需求或新的独立协议 consumer 提供实际证据时，再确定 Owner 和验证边界；不以跨进程同步恢复重复状态。
