# 后端业务优先目录与文件迁移提案

状态：proposed
类型：architecture
Owner：backend/pyproject.toml

## 问题

本提案面向后端维护者，基于 2026-09-29 工作目录中的实际源码，定义从 `backend/yuxi/` 开始的目标文件树和来源映射。目标目录现已落到工作树；本文保留逐文件来源映射。生产链路的完整验收尚未执行，故记录仍处于 proposed。

后端入口与业务实现分别位于 `backend/server` 和 `backend/package/yuxi`，业务服务、repository、运行时和资源管理采用不同归组方式。目标是合并后端项目边界，以业务模块组织用例与持久化，并明确 HTTP、worker、技术设施和启动装配的位置。

非目标：本次目录迁移不主动修改公开协议、数据库表、队列状态与权限规则；不引入微服务、通用事件总线、统一状态机或全量抽象接口。

## 提案

### 实现方案

保留一个 Python 导入命名空间 `yuxi` 和一份后端项目配置。HTTP 与 worker 作为应用入口；业务模块拥有用例、事务和 repository；基础设施提供连接与技术适配；bootstrap 拥有启动装配。共享 Schema 初始化入口，保留当前 business 与 knowledge 两套 PostgreSQL metadata；业务 ORM 定义随其业务模块归组。

项目装配事实来自后端项目配置（`backend/pyproject.toml`）、API 入口（`backend/yuxi/api/main.py`）、worker 执行与装配（`backend/yuxi/workers/main.py`、`backend/yuxi/bootstrap/worker.py`）和 Compose（`docker-compose.yml`）。当前业务边界由 ARCHITECTURE.md 与源码拥有；本文件保存来源与目标的迁移映射。

普通输入继续由 Agent 模块接收并持久化，经 FIFO 创建 Turn/Run，在事务提交后投递 worker；worker 调用同域 runner 执行、收敛终态并发布事件。知识文件和聊天附件共同调用 documents 的配置感知解析入口，再调用 infrastructure 的解析引擎；知识文件的状态、分块与索引仍由 knowledge 拥有。schedules 调用统一 Agent 输入用例，background_jobs 保留独立持久作业状态。

目录调整分为机械迁移和职责拆分两类交付。迁移阶段保持既有公开函数契约；树中明确标注的拆分、合并各自单独验证。现有 service 中零散的 HTTPException、部分 router 内部查询和 knowledge manager/base 的宽职责不在此提案中全量重构；本树不宣称已经实现完全无框架依赖的业务层。抽出的 HTTP 响应和资源清理必须在同一次局部变更中接通调用方。

### 目标文件树

这是一份目标结构快照，所有目标路径均相对 `backend/yuxi/`。来源前缀 `Y/` = `backend/package/yuxi/`，`S/` = `backend/server/`。`[移]` 为文件迁移，`[移改]` 同时重命名或收窄原入口，`[整移]` 为目录整体迁移，`[拆]` 为从来源文件抽取一部分，`[合]` 为合并多个来源中的指定职责，`[新]` 为装配需要的新文件。

整体迁移表示内部文件布局和业务职责保留，仍需机械修正 import、动态注册字符串及资源定位。存在内部新增、拆分或合并的目录全部展开。树列出具有职责的文件与现有 initializer；新增目录只在工具链或注册需求实际要求时补空 `__init__.py`，不在本提案批量制造空文件。

```text
backend/yuxi/
├── api/
│   ├── dependencies/
│   │   ├── auth.py  # [移改] S/utils/auth_middleware.py；JWT/API Key 身份解析与 FastAPI Depends
│   │   └── knowledge.py  # [移改] S/utils/knowledge_permissions.py；知识库可见性与管理权限的 HTTP 依赖
│   ├── middleware/
│   │   └── access_log.py  # [移改] S/utils/access_log_middleware.py；HTTP 请求日志
│   ├── responses/
│   │   ├── files.py  # [合] Y/services/file_preview.py + Y/services/artifact_service.py + Y/services/workspace_service.py + Y/services/viewer_filesystem_service.py；预览与下载响应装配、BackgroundTask 清理；文件读取与授权保留在原业务用例
│   │   └── knowledge.py  # [移改] S/utils/knowledge_response.py；知识库读取模型的协议序列化
│   ├── routers/
│   │   ├── agents/
│   │   │   ├── management.py  # [移改] S/routers/agent_router.py；URL、认证依赖与响应契约保留
│   │   │   └── mentions.py  # [移改] S/routers/mention_router.py；URL、认证依赖与响应契约保留
│   │   ├── extensions/
│   │   │   ├── mcp.py  # [移改] S/routers/mcp_router.py；URL、认证依赖与响应契约保留
│   │   │   ├── skills.py  # [移改] S/routers/skill_router.py；URL、认证依赖与响应契约保留
│   │   │   └── tools.py  # [移改] S/routers/tool_router.py；URL、认证依赖与响应契约保留
│   │   ├── identity/
│   │   │   ├── auth.py  # [移改] S/routers/auth_router.py；URL、认证依赖与响应契约保留
│   │   │   ├── departments.py  # [移改] S/routers/auth_dept_router.py；URL、认证依赖与响应契约保留
│   │   │   ├── oidc.py  # [拆] Y/services/oidc_service.py；现有 *_handler 与重定向响应的 HTTP 部分；业务部分调用 identity.oidc
│   │   │   └── users.py  # [移改] S/routers/user_router.py；URL、认证依赖与响应契约保留
│   │   ├── knowledge/
│   │   │   ├── dashboard.py  # [移改] S/routers/knowledge_dashboard_router.py；URL、认证依赖与响应契约保留
│   │   │   ├── evaluation.py  # [移改] S/routers/knowledge_eval_router.py；URL、认证依赖与响应契约保留
│   │   │   ├── external.py  # [移改] S/routers/external_kb_router.py；URL、认证依赖与响应契约保留
│   │   │   ├── graphs.py  # [移改] S/routers/graph_router.py；URL、认证依赖与响应契约保留
│   │   │   └── management.py  # [移改] S/routers/knowledge_router.py；URL、认证依赖与响应契约保留
│   │   ├── public_v1/  # [整移] S/routers/public_v1/；保留 agents Thread/Session 与 knowledge 公开协议；仅修正内部调用路径
│   │   ├── workspace/
│   │   │   ├── projects.py  # [移改] S/routers/project_router.py；URL、认证依赖与响应契约保留
│   │   │   ├── viewer.py  # [移改] S/routers/filesystem_router.py；URL、认证依赖与响应契约保留
│   │   │   └── workspace.py  # [移改] S/routers/workspace_router.py；URL、认证依赖与响应契约保留
│   │   ├── __init__.py  # [移改] S/routers/__init__.py；保留完整能力注册、挂载前缀及兼容路由
│   │   ├── dashboard.py  # [移改] S/routers/dashboard_router.py；URL、认证依赖与响应契约保留
│   │   ├── models.py  # [移改] S/routers/model_provider_router.py；URL、认证依赖与响应契约保留
│   │   ├── schedules.py  # [移改] S/routers/scheduled_agent_router.py；URL、认证依赖与响应契约保留
│   │   ├── system.py  # [移改] S/routers/system_router.py；URL、认证依赖与响应契约保留
│   │   └── background_jobs.py  # [移改] S/routers/system_task_router.py；后台作业查询、取消与删除
│   ├── lifespan.py  # [拆] S/utils/lifespan.py；FastAPI lifespan 与 app.state 适配
│   ├── main.py  # [移改] S/main.py；FastAPI 应用与现有中间件装配
│   └── sse.py  # [拆] Y/utils/sse_utils.py；仅 format_sse、format_heartbeat；订阅时序配置归 Agent events
├── bootstrap/
│   ├── api.py  # [拆] S/utils/lifespan.py；组件初始化、关闭顺序与必需/可选组件结果
│   ├── environment.py  # [拆] Y/__init__.py；load_dotenv；三个进程入口在依赖初始化前调用
│   ├── models.py  # [新] 无旧文件；显式导入各业务 ORM，装配两套既有 metadata；不修改 schema 域
│   ├── background_job_handlers.py  # [拆] Y/services/task_registry.py；JOB_DEFINITIONS 注册；保持 job_type/handler_version 与惰性导入
│   └── worker.py  # [拆] Y/services/run_worker.py；startup/shutdown、恢复循环启动与共享资源释放
├── infrastructure/
│   ├── document_parsing/
│   │   ├── __init__.py  # 轻量 ParseOptions、ParseResult 与异常契约
│   │   ├── parser.py  # 唯一本地解析流程与格式转换
│   │   ├── artifacts.py  # 相对资源、Markdown 引用与 ZIP 安全提取
│   │   ├── pdf_utils.py  # PDF page tree 校验
│   │   └── engines/  # 引擎契约、元数据、惰性装配与具体 OCR 适配器
│   ├── minio/  # [整移] Y/storage/minio/；内部结构保留，仅修正导入与资源定位
│   │   └── object_urls.py  # MinIO URL 识别与解析，共享对象定位，不执行知识库权限决策
│   ├── neo4j/  # [整移] Y/storage/neo4j/；内部结构保留，仅修正导入与资源定位
│   ├── observability/
│   │   ├── langfuse.py  # [拆] Y/services/langfuse_service.py；SDK/client、启用检测、flush、远端 URL/score 传输；不读取业务终态
│   │   └── logging.py  # [合] Y/utils/logging_config.py + S/utils/common_utils.py；日志配置与 setup_logging；核对配置时序后合并
│   ├── oidc/
│   │   └── client.py  # [拆] Y/services/oidc_service.py；Provider metadata、discovery、token/userinfo HTTP 和协议校验；不读用户表
│   ├── postgres/
│   │   ├── base.py  # [合] Y/storage/postgres/models_business.py + Y/storage/postgres/models_knowledge.py；BusinessBase、KnowledgeBase 两个既有 registry/metadata 与 JSON_VALUE；不合并 schema 域
│   │   ├── checkpointer.py  # [拆] Y/storage/postgres/manager.py；LangGraph PG checkpoint pool 与 saver 生命周期
│   │   ├── manager.py  # [拆] Y/storage/postgres/manager.py；业务 engine/session/连接生命周期；迁移方法移出
│   │   └── schema.py  # [拆] Y/storage/postgres/manager.py；schema 版本常量、读取和兼容检查；API/worker 只读检查
│   ├── redis/  # [整移] Y/storage/redis/；内部结构保留，仅修正导入与资源定位
│   ├── file_preview.py  # [拆] Y/utils/filepreview.py；展示类型判断与预览内容准备，公共文件结果与 MIME 识别归 shared/files.py
│   ├── office_conversion.py  # [拆] Y/utils/filepreview.py；独立 Office 到 PDF 转换工具
│   ├── filesystem.py  # [移改] Y/utils/paths.py；跨 Workspace/Skills 的 no-follow 文件描述符原语
│   ├── images.py  # [移改] Y/utils/image_processor.py；图像校验、压缩与缩略图
│   ├── runtime_settings.py  # [移改] Y/config/__init__.py；进程环境与运行目录配置，不再转发用户配置
│   ├── object_urls.py  # 删除；MinIO URL 识别与解析归入 infrastructure/minio/object_urls.py，不接收知识库权限决策
│   └── uploads.py  # [移改] Y/utils/upload_utils.py；有界异步流读取与写入；参数依赖 read/seek 协议，移除 FastAPI 类型依赖
├── migrations/
│   ├── main.py  # [移改] Y/storage_migration.py；仅为全新部署初始化当前 Schema，拒绝旧版本
│   └── schema.py  # [拆] Y/storage/postgres/manager.py；初始化锁、版本写入、建表和当前 Schema DDL；仅 schema-init 调用
├── modules/
│   ├── agents/
│   │   ├── models/
│   │   │   ├── definitions.py  # [拆] Y/storage/postgres/models_business.py；Agent、AgentEnv
│   │   │   ├── inputs.py  # [拆] Y/storage/postgres/models_business.py；AgentInput、AgentInputReceipt、AgentInputMessage
│   │   │   ├── messages.py  # [拆] Y/storage/postgres/models_business.py；Message、ToolCall、MessageFeedback、审计消息类型常量
│   │   │   ├── runs.py  # [拆] Y/storage/postgres/models_business.py；AgentRun、AgentRunAttempt、Run 约束/状态常量与 build_agent_run_timing
│   │   │   ├── threads.py  # [拆] Y/storage/postgres/models_business.py；Conversation、SubagentThread、ConversationStats、线程初始已读标记
│   │   │   └── turns.py  # [拆] Y/storage/postgres/models_business.py；AgentTurn
│   │   ├── presets/  # [整移] Y/agents/presets/；内部结构保留，仅修正导入与资源定位
│   │   ├── repositories/
│   │   │   ├── __init__.py  # [移] Y/repositories/agents/__init__.py
│   │   │   ├── definitions.py  # [移改] Y/repositories/agent_repository.py
│   │   │   ├── environment.py  # [移改] Y/repositories/agent_env_repository.py
│   │   │   ├── input.py  # [移] Y/repositories/agents/input.py
│   │   │   ├── input_receipt.py  # [移] Y/repositories/agents/input_receipt.py
│   │   │   ├── model_audit.py  # [移改] Y/repositories/model_message_audit_repository.py
│   │   │   ├── runs.py  # [移改] Y/repositories/agent_run_repository.py
│   │   │   ├── state.py  # [移改] Y/repositories/agent_state_repository.py
│   │   │   ├── subagents.py  # [移改] Y/repositories/subagent_thread_repository.py
│   │   │   ├── threads.py  # [移改] Y/repositories/conversation_repository.py
│   │   │   ├── tool_audit.py  # [移改] Y/repositories/tool_message_audit_repository.py
│   │   │   └── turn.py  # [移] Y/repositories/agents/turn.py
│   │   ├── runtime/
│   │   │   ├── backends/  # [整移] Y/agents/backends/；内部结构保留，仅修正导入与资源定位
│   │   │   ├── builtin/  # [整移] Y/agents/buildin/；目录拼写统一为 builtin；后端注册、ID 和内部结构保留
│   │   │   ├── callbacks/  # [整移] Y/agents/callbacks/；内部结构保留，仅修正导入与资源定位
│   │   │   ├── middlewares/  # [整移] Y/agents/middlewares/；内部结构保留，仅修正导入与资源定位
│   │   │   ├── __init__.py  # [移] Y/agents/__init__.py
│   │   │   ├── base.py  # [移] Y/agents/base.py
│   │   │   ├── context.py  # [移] Y/agents/context.py
│   │   │   ├── questions.py  # [移改] Y/utils/question_utils.py；人工问题规范化与展示数据
│   │   │   ├── state.py  # [移] Y/agents/state.py
│   │   │   └── tool_approval.py  # [移] Y/agents/tool_approval.py
│   │   └── services/
│   │       ├── artifacts.py  # [拆] Y/services/artifact_service.py；保留授权、文件读取与业务结果；HTTP 下载/预览响应并入 api/responses/files.py
│   │       ├── attachments.py  # [移改] Y/services/attachment_service.py；随 Agent 业务归组
│   │       ├── commands.py  # [移改] Y/services/channel_command_service.py；随 Agent 业务归组
│   │       ├── compression.py  # [移改] Y/services/context_compression_service.py；随 Agent 业务归组
│   │       ├── configuration.py  # [移改] Y/services/agent_config_service.py；随 Agent 业务归组
│   │       ├── directory.py  # [移] Y/services/agents/directory.py；保留现有职责
│   │       ├── event_writer.py  # [拆] Y/services/run_worker.py；ChunkedEventWriter、chunk 映射、缓冲刷新、append_run_event 与 end event；共享发布 helper 公开命名
│   │       ├── events.py  # [移] Y/services/agents/events.py；保留现有职责
│   │       ├── execution.py  # [移] Y/services/agents/execution.py；保留现有职责
│   │       ├── feedback.py  # [移改] Y/services/feedback_service.py；随 Agent 业务归组
│   │       ├── input_config.py  # [移] Y/services/agents/input_config.py；保留现有职责
│   │       ├── input_messages.py  # [移] Y/services/agents/input_messages.py；保留现有职责
│   │       ├── inputs.py  # [移] Y/services/agents/inputs.py；保留现有职责
│   │       ├── leases.py  # [拆] Y/services/run_worker.py；领取/续租/释放、过期 Run 与清理恢复、release_runtime_if_idle；不回引 runner
│   │       ├── memory.py  # [移改] Y/services/memory_service.py；随 Agent 业务归组
│   │       ├── mentions.py  # [移改] Y/services/mention_search_service.py；随 Agent 业务归组
│   │       ├── messages.py  # [移] Y/services/agents/messages.py；保留现有职责
│   │       ├── model_audit.py  # [移改] Y/services/model_message_audit_service.py；随 Agent 业务归组
│   │       ├── preparation.py  # [移] Y/services/agents/preparation.py；保留现有职责
│   │       ├── runner.py  # [拆] Y/services/run_worker.py；process_agent_run 主流程、RunContext、取消、终态与 runtime 清理
│   │       ├── runs.py  # [移] Y/services/agents/runs.py；保留现有职责
│   │       ├── scheduler.py  # [移] Y/services/agents/scheduler.py；保留现有职责
│   │       ├── scope.py  # [移] Y/services/agents/scope.py；保留现有职责
│   │       ├── state.py  # [移] Y/services/agents/state.py；保留现有职责
│   │       ├── subagents.py  # [移改] Y/services/subagent_run_service.py；随 Agent 业务归组
│   │       ├── threads.py  # [移] Y/services/agents/threads.py；保留现有职责
│   │       ├── tool_audit.py  # [移改] Y/services/tool_message_audit_service.py；随 Agent 业务归组
│   │       ├── tracing.py  # [拆] Y/services/langfuse_service.py；Turn/Run trace 归属、PG 终态投影与反馈语义
│   │       ├── transport.py  # [移] Y/services/agents/transport.py；保留现有职责
│   │       └── turns.py  # [移] Y/services/agents/turns.py；保留现有职责
│   ├── documents/
│   │   ├── assets.py  # [合] Y/knowledge/parser/unified.py + Y/knowledge/parser/zip_utils.py；按明确 bucket/prefix 上传完整解析资源并构造 hosted Markdown
│   │   └── service.py  # [移改] Y/services/ocr_service.py；配置感知 parse、parse_to_hosted_markdown、引擎配置/凭据解析和健康检查；重型 parser 惰性加载
│   ├── extensions/
│   │   ├── mcp/
│   │   │   ├── __init__.py  # [移] Y/agents/mcp/__init__.py
│   │   │   ├── builtin.py  # [移] Y/agents/mcp/builtin.py
│   │   │   ├── models.py  # [拆] Y/storage/postgres/models_business.py；MCPServer
│   │   │   ├── repository.py  # [拆] Y/agents/mcp/service.py；MCPServer SQL 查询与写入；事务仍由原用例拥有
│   │   │   ├── runtime.py  # [拆] Y/agents/mcp/service.py；工具加载、缓存、transport 约束与 disabled_tools 应用
│   │   │   └── service.py  # [拆] Y/agents/mcp/service.py；内置同步、CRUD 编排与工具启停策略
│   │   ├── skills/
│   │   │   ├── builtin/  # [整移] Y/agents/skills/buildin/；内置 SKILL.md 与 scripts 原样保留；仅目录名 buildin → builtin
│   │   │   ├── __init__.py  # [移] Y/agents/skills/__init__.py
│   │   │   ├── models.py  # [拆] Y/storage/postgres/models_business.py；Skill
│   │   │   ├── catalog.py  # [拆] Y/services/skills/catalog.py；共享与个人 Skill 的展示目录
│   │   │   ├── draft.py  # [拆] Y/services/skills/draft.py；安装草稿与可确认条目
│   │   │   ├── edit.py  # [拆] Y/services/skills/edit.py；修订值、共享文件编辑、回滚与锁
│   │   │   ├── package.py  # [拆] Y/services/skills/package.py；包解析与安全复制
│   │   │   ├── personal.py  # [拆] Y/services/skills/personal.py；个人 Skill 用例与 UserWorkspace 边界
│   │   │   ├── projection.py  # [合] Y/services/skills/projection.py；授权快照、共享行锁与用户投影发布
│   │   │   ├── remote.py  # [移改] Y/services/skills/remote.py；远程发现与目录下载
│   │   │   ├── repository.py  # [移] Y/repositories/skill_repository.py；可见性与行锁查询
│   │   │   ├── resolved.py  # [拆] Y/services/skills/resolved.py；Skill 来源描述
│   │   │   ├── runtime.py  # [移] Y/agents/skills/runtime.py；持锁读取运行快照
│   │   │   └── shared.py  # [拆] Y/services/skills/shared.py；共享索引、授权、安装与内置同步
│   │   └── tools/
│   │       ├── builtin/  # [整移] Y/agents/toolkits/buildin/；内部结构保留，仅修正导入与资源定位
│   │       ├── debug/  # [整移] Y/agents/toolkits/debug/；内部结构保留，仅修正导入与资源定位
│   │       ├── knowledge/  # [整移] Y/agents/toolkits/kbs/；内部结构保留，仅修正导入与资源定位
│   │       ├── __init__.py  # [移] Y/agents/toolkits/__init__.py
│   │       ├── catalog.py  # [拆] Y/agents/toolkits/service.py；工具元数据缓存、按分类列举
│   │       ├── registry.py  # [移] Y/agents/toolkits/registry.py
│   │       ├── runtime.py  # [拆] Y/agents/toolkits/service.py；resolve_configured_runtime_tools；本地/MCP/Skill 工具组装和冲突拒绝
│   │       └── utils.py  # [移] Y/agents/toolkits/utils.py
│   ├── identity/
│   │   ├── permissions/  # [整移] Y/permissions/；跨资源权限规则保留；最终权限仍由 executor/repository 执行
│   │   ├── repositories/
│   │   │   ├── api_keys.py  # [移改] Y/repositories/api_key_repository.py
│   │   │   ├── departments.py  # [移改] Y/repositories/department_repository.py
│   │   │   └── users.py  # [移改] Y/repositories/user_repository.py
│   │   ├── services/
│   │   │   ├── administration.py  # [移改] Y/services/identity_admin_service.py
│   │   │   ├── cli_auth.py  # [移改] Y/services/auth_service.py
│   │   │   ├── login_limits.py  # [移改] Y/services/login_rate_limit_service.py
│   │   │   └── usernames.py  # [移改] Y/services/user_identity_service.py
│   │   ├── models.py  # [拆] Y/storage/postgres/models_business.py；User、Department、UserConfig、APIKey、CLIAuthSession、登录锁定常量
│   │   ├── oidc.py  # [拆] Y/services/oidc_service.py；OIDCConfig 与用户绑定、恢复、创建和授权业务；纯协议调用交给 client
│   │   ├── preferences.py  # [移改] Y/config/user.py；用户配置持久化和 schema
│   │   └── security.py  # [移改] Y/utils/auth_utils.py；JWT、密码、API Key 派生和安全配置校验
│   ├── knowledge/
│   │   ├── chunking/  # [整移] Y/knowledge/chunking/；内部结构保留，仅修正导入与资源定位
│   │   ├── evaluation/  # [整移] Y/knowledge/eval/；重命名 eval；评估服务、计算与任务 handler 保留内部结构
│   │   ├── graphs/  # [整移] Y/knowledge/graphs/；内部结构保留，仅修正导入与资源定位
│   │   ├── implementations/  # [整移] Y/knowledge/implementations/；内部结构保留，仅修正导入与资源定位
│   │   ├── repositories/
│   │   │   ├── bases.py  # [移改] Y/repositories/knowledge_base_repository.py
│   │   │   ├── chunks.py  # [移改] Y/repositories/knowledge_chunk_repository.py
│   │   │   ├── evaluation.py  # [移改] Y/repositories/evaluation_repository.py
│   │   │   ├── files.py  # [移改] Y/repositories/knowledge_file_repository.py
│   │   │   └── graphs.py  # [移改] Y/repositories/knowledge_graph_repository.py
│   │   ├── services/
│   │   │   ├── __init__.py  # [移] Y/services/knowledge/__init__.py
│   │   │   ├── dashboard.py  # [移改] Y/services/knowledge_dashboard_service.py
│   │   │   ├── folders.py  # [移改] Y/services/knowledge_folder_service.py
│   │   │   ├── background_jobs.py  # [移改] Y/services/knowledge_task_service.py
│   │   │   └── tools.py  # [移] Y/services/knowledge/tools.py
│   │   ├── utils/
│   │   │   ├── __init__.py  # [移] Y/knowledge/utils/__init__.py
│   │   │   ├── kb_utils.py  # [拆] Y/knowledge/utils/kb_utils.py；保留知识参数、文件元数据与知识图片代理 URL；通用对象定位函数下沉
│   │   │   ├── sample_question_utils.py  # [移] Y/knowledge/utils/sample_question_utils.py
│   │   │   ├── security.py  # [移] Y/knowledge/utils/security.py
│   │   │   ├── url_fetcher.py  # [移] Y/knowledge/utils/url_fetcher.py
│   │   │   └── url_validator.py  # [移] Y/knowledge/utils/url_validator.py
│   │   ├── __init__.py  # [移] Y/knowledge/__init__.py；保留现有域内职责；runtime 的实例生命周期由 bootstrap 调用
│   │   ├── base.py  # [移] Y/knowledge/base.py；保留现有域内职责；runtime 的实例生命周期由 bootstrap 调用
│   │   ├── cache.py  # [移] Y/knowledge/cache.py；保留现有域内职责；runtime 的实例生命周期由 bootstrap 调用
│   │   ├── factory.py  # [移] Y/knowledge/factory.py；保留现有域内职责；runtime 的实例生命周期由 bootstrap 调用
│   │   ├── manager.py  # [移] Y/knowledge/manager.py；保留现有域内职责；runtime 的实例生命周期由 bootstrap 调用
│   │   ├── models.py  # [拆] Y/storage/postgres/models_knowledge.py；保留全部知识/图谱/评估 ORM；Base 与 JSON_VALUE 移至共享数据库定义
│   │   ├── preview.py  # [移] Y/knowledge/preview.py；保留现有域内职责；runtime 的实例生命周期由 bootstrap 调用
│   │   ├── read_models.py  # [移] Y/knowledge/read_models.py；保留现有域内职责；runtime 的实例生命周期由 bootstrap 调用
│   │   ├── runtime.py  # [移] Y/knowledge/runtime.py；保留现有域内职责；runtime 的实例生命周期由 bootstrap 调用
│   │   └── schemas.py  # [移] Y/knowledge/schemas.py；保留现有域内职责；runtime 的实例生命周期由 bootstrap 调用
│   ├── models/
│   │   ├── providers/  # [整移] Y/models/providers/；供应商 service/repository/cache 同域保留；不再拆到全局层
│   │   ├── __init__.py  # [移] Y/models/__init__.py
│   │   ├── chat.py  # [移] Y/models/chat.py
│   │   ├── embed.py  # [移] Y/models/embed.py
│   │   ├── rerank.py  # [移] Y/models/rerank.py
│   │   ├── tables.py  # [拆] Y/storage/postgres/models_business.py；ModelProvider；区别于 LLM 模型适配器
│   │   └── utils.py  # [移] Y/models/utils.py
│   ├── schedules/
│   │   ├── models.py  # [拆] Y/storage/postgres/models_business.py；ScheduledAgentJob、ScheduledAgentRun
│   │   ├── repository.py  # [移改] Y/repositories/scheduled_agent_repository.py
│   │   └── service.py  # [移改] Y/services/scheduled_agent_service.py；定时定义、occurrence、到期领取、调用统一 Agent 输入用例
│   ├── system/
│   │   ├── static/
│   │   │   └── info.template.yaml  # [移改] Y/config/static/info.template.yaml；站点品牌模板
│   │   ├── repositories/
│   │   │   └── dashboard.py  # [移改] Y/repositories/dashboard_repository.py；跨域只读统计；不写其他业务状态
│   │   ├── dashboard.py  # [移改] Y/services/dashboard_service.py
│   │   ├── models.py  # [拆] Y/storage/postgres/models_business.py；ConfigOption
│   │   ├── options.py  # [移改] Y/config/options.py；系统级持久配置、缓存与失效
│   │   └── readiness.py  # [移改] Y/services/readiness_service.py
│   ├── background_jobs/
│   │   ├── models.py  # [拆] Y/storage/postgres/models_business.py；BackgroundJobRecord
│   │   ├── dispatch.py  # [拆] Y/services/task_queue_service.py；API 提交与事务提交后投递
│   │   ├── registry.py  # [拆] Y/services/task_registry.py；共享作业定义与版本校验
│   │   ├── repository.py  # [移改] Y/repositories/task_repository.py
│   │   └── service.py  # [移改] Y/services/task_service.py；BackgroundJob/JobTracker 登记、观察与取消请求
│   └── workspace/
│       ├── repositories/
│       │   └── projects.py  # [移改] Y/repositories/project_repository.py
│       ├── services/
│       │   ├── bindings.py  # [移改] Y/services/workdir_service.py
│       │   ├── files.py  # [拆] Y/services/workspace_service.py；保留授权、文件读取与业务结果；HTTP 下载/预览响应并入 api/responses/files.py
│       │   ├── projects.py  # [移改] Y/services/project_service.py
│       │   └── viewer.py  # [拆] Y/services/viewer_filesystem_service.py；保留授权、文件读取与业务结果；HTTP 下载/预览响应并入 api/responses/files.py
│       ├── __init__.py  # [移] Y/workspace/__init__.py
│       ├── errors.py  # [移] Y/workspace/errors.py
│       ├── filesystem.py  # [移] Y/workspace/filesystem.py
│       ├── models.py  # [拆] Y/storage/postgres/models_business.py；Project、Project 状态约束
│       ├── paths.py  # [移] Y/workspace/paths.py
│       ├── preview.py  # [移] Y/workspace/preview.py
│       └── workdir.py  # [移] Y/workspace/workdir.py
├── shared/
│   ├── datetime.py  # [移改] Y/utils/datetime_utils.py
│   ├── files.py  # [新] 无旧文件；下载结果的数据契约：内容/临时路径、媒体类型、文件名与清理责任；由 Agent/Workspace 用例生产、API 消费
│   ├── hashing.py  # [移改] Y/utils/hash_utils.py
│   ├── singleton.py  # [移改] Y/utils/singleton.py
│   └── strings.py  # [移改] Y/utils/string_utils.py
├── workers/
│   ├── arq.py  # [移改] Y/services/arq_worker.py；YuxiWorker 领取适配
│   ├── health.py  # [移改] Y/services/worker_health.py；worker healthcheck 命令与进程健康协议
│   ├── main.py  # [移改] S/worker_main.py；ARQ 启动入口与 Windows event loop 设置
│   ├── settings.py  # [拆] Y/services/run_worker.py；WorkerSettings、worker_max_jobs；注册既有 job 名称与参数
│   ├── background_job_context.py  # [拆] Y/services/task_service.py；领域执行方的上报、取消检查与 owner 保护
│   └── background_jobs.py  # [拆] Y/services/task_service.py；后台 Handler 执行、lease 与领域终态 Hook
└── __init__.py  # [拆] Y/__init__.py；保留版本查询；显式启动时加载环境；无消费者 executor 见退役说明
```

### 拆分与合并的具体边界

本节补充树中不能仅靠 rename 完成的变更。下列目标均相对 `backend/yuxi/`；未明确抽出的职责留在表中指定的主要承接文件，不根据行数继续拆 helper。

| 来源 | 目标与职责分配 | 保持的边界 |
|---|---|---|
| `Y/services/run_worker.py` | `workers/settings.py` 承接 WorkerSettings 与并发参数；`bootstrap/worker.py` 承接 startup/shutdown、周期循环与健康发布的接线；`modules/agents/services/leases.py` 承接 mark_run_running、renew_run_lease、release_run_lease_for_retry、reconcile_expired_run_leases、reconcile_pending_runtime_cleanups，以及公开命名后的 release_runtime_if_idle；`event_writer.py` 承接 ChunkedEventWriter、chunk 映射、append_run_event 及发布/flush/end helper，共享 helper 去掉私有前缀；`runner.py` 承接 process_agent_run、RunContext、mark_run_terminal、清理异常包装、取消及其余执行 helper。 | runner → leases/event_writer，leases 可调用事件发布与同域清理原语，但不回引 runner。lease 与终态事务只拥有一份实现。worker 注册原 job 名称；bootstrap 只启动周期循环。 |
| `S/utils/lifespan.py` | `bootstrap/api.py` 承接初始化/关闭操作及其必需性策略；`api/lifespan.py` 承接 FastAPI lifespan 与 app.state 发布。 | 保留依赖初始化顺序、失败退出、结构化 readiness 信息及共享资源释放。 |
| `Y/storage/postgres/manager.py` | `infrastructure/postgres/manager.py` 保留连接、session、关闭与运行期辅助；`checkpointer.py` 承接 checkpoint pool/saver；`schema.py` 承接版本常量、查询与 require_current_schema；`migrations/schema.py` 承接初始化锁、schema 版本写入、建表与当前 DDL，包括 ensure_business_schema、ensure_knowledge_schema。 | API/worker 只校验 schema；DDL 仍由唯一 schema-init 执行。运行期代码不导入迁移执行模块。 |
| `Y/storage/postgres/models_business.py`、`models_knowledge.py` | 按树中列出的类归属拆 ORM；两个 Base 与 JSON_VALUE 进入 `infrastructure/postgres/base.py`；`infrastructure/postgres/models.py` 显式加载全部 ORM。 | 保留两个 registry/metadata、表名、约束名、FK、默认值及 relationship 字符串。每个映射类只注册一次。UNVIEWED_RUN_MARKER 跟随 threads，权限锁定常量跟随 identity，其余常量按树中归属移动。 |
| `Y/knowledge/parser/unified.py`、`Y/services/ocr_service.py` | `infrastructure/document_parsing/parser.py` 生成完整本地目录；`modules/documents/service.py` 解析配置与 MinIO 输入，`assets.py` 按明确归属发布资源。 | 解析不上传图片，聊天完整保存本地目录，知识库在发布阶段提供文档归属与代理 URL。详见[文档解析边界](../implemented/2026-09-30-document-parsing-artifacts.md)。 |
| `Y/knowledge/utils/kb_utils.py` | `is_minio_url`、`parse_minio_url` 进入 `infrastructure/minio/object_urls.py`；知识库图片 URL、文件元数据与处理参数留在 `modules/knowledge/utils/kb_utils.py`。 | URL 字符串解析不授权对象访问；授权仍在读取与执行边界。共享 parser 不再反向依赖 knowledge。 |
| `Y/agents/skills/service.py` 与上游 `Y/services/skills/` | 用例归组于 `modules/extensions/skills`，按 shared、personal、draft、edit、projection、catalog 和 package 分工。详见[Skill 模块边界](../implemented/2026-09-29-skill-module-ownership.md)。 | 投影用例拥有授权快照与锁顺序；编辑与运行时采用同一共享行锁协议。 |
| `Y/agents/mcp/service.py` | `modules/extensions/mcp/repository.py` 承接 SQL 查询/写入；`runtime.py` 承接 MultiServerMCPClient、工具缓存、加载和过滤；`service.py` 保留内置同步、CRUD/启停编排、运行配置与资源策略。 | service 解析配置后传给 runtime；runtime 不反向导入 service。缓存失效、transport 限制、工具名称与 disabled_tools 行为保留。 |
| `Y/agents/toolkits/service.py` | `modules/extensions/tools/catalog.py` 承接元数据缓存与目录查询；`runtime.py` 承接 resolve_configured_runtime_tools。 | 本地、MCP、Skill 工具仍使用同一冲突判定与运行装配；builtin 重命名只改目录，保留已有工具 ID、类别值与内置 slug。 |
| `Y/services/oidc_service.py` | `modules/identity/oidc.py` 保留 OIDCConfig、用户绑定/恢复/创建、state/nonce、一次性交换码和其余登录业务；`infrastructure/oidc/client.py` 承接 ProviderMetadata、discovery、token/userinfo 网络与协议操作；`api/routers/identity/oidc.py` 承接 handler 的 HTTP 参数/响应与重定向。 | OIDCUtils 按方法职责拆分，不整类搬到 infrastructure。保留 state/nonce、一次性消费和失败路径，不在本次重做认证策略。 |
| `Y/services/langfuse_service.py` | `infrastructure/observability/langfuse.py` 承接启用检测、SDK/client、flush、远端操作及 `_export_turn_root` 的协议发送；`modules/agents/services/tracing.py` 承接 LangfuseRunContext、trace metadata/tags、Turn/Run observation 归属、finish_turn_observation_if_terminal 与业务反馈。 | infrastructure 接收已经确定的 ID/状态；读取 PG Turn 终态的逻辑留在 Agent 模块。远端 trace 不拥有业务成功/失败事实。 |
| `Y/services/file_preview.py`、artifact/workspace/viewer service | `api/responses/files.py` 统一装配 FileResponse/StreamingResponse 与 BackgroundTask；原业务 service 保留授权、文件读取/准备和保存操作，返回 `shared/files.py` 的文件结果。 | 服务准备失败时自行清理；交付给 HTTP 后，响应装配负责关闭与临时文件清理。取消、断开和响应构造失败都要验证；不提前删除流正在读取的文件。 |
| `Y/utils/logging_config.py`、`S/utils/common_utils.py` | 合并到 `infrastructure/observability/logging.py`，保留现有 logger 导出与 setup_logging 入口，由 bootstrap 显式调用。 | 保留应用 logger 与 Uvicorn/标准 logging 的各自配置，不借合并替换日志库或修改输出格式。 |
| `Y/services/task_registry.py` | `modules/background_jobs/registry.py` 保留 JobDefinition、解析版本与加载行为；`bootstrap/background_job_handlers.py` 保留实际业务 handler 注册表，API/worker 初始化时显式注册。 | 任务 type/version 不变；模块路径随迁移更新，handler 继续惰性加载。registry 未完成装配时显式报错，不能以空表伪装可用。 |
| `Y/__init__.py`、`Y/config/__init__.py` | 根 initializer 保留版本查询；dotenv 加载进入 bootstrap/environment；进程环境与运行目录配置进入 infrastructure/runtime_settings；持久系统配置进入 system/options，用户配置进入 identity/preferences。 | API、worker、schema-init 在导入会读取配置的模块前加载环境；保留当前环境覆盖语义。生产 metadata 仍能正确返回 Yuxi 版本。 |
| `Y/utils/sse_utils.py` | format_sse、format_heartbeat 进入 `api/sse.py`；使用中的 SSE_HEARTBEAT_SECONDS、SSE_MAX_CONNECTION_MINUTES 由 `modules/agents/services/subscriptions.py` 拥有。 | SSE 编码仍只在 HTTP 边界发生一次；无人使用的轮询配置不再导出。 |

拆分的直接检查点来自 worker（`backend/package/yuxi/services/run_worker.py`）、解析配置入口（`backend/package/yuxi/services/ocr_service.py`）、parser（`backend/package/yuxi/knowledge/parser/unified.py`）、Skills 授权与投影（`backend/package/yuxi/agents/skills/service.py`） 和 数据库 manager（`backend/package/yuxi/storage/postgres/manager.py`）。这些路径记录迁移前来源；当前 Owner 由目标树与 ARCHITECTURE.md 指定。

### 不进入目标树的文件与旧导出

| 来源 | 去向与移除条件 |
|---|---|
| `Y/main.py` | 仅输出 Hello from yuxi 的占位入口退役；正式入口改为 API、worker 和 schema-init。当前仓库内未找到该模块作为进程入口的调用。 |
| `Y/repositories/__init__.py` | 全局 repository 聚合目录取消；调用方导入所属业务模块。 |
| `Y/utils/__init__.py` | logger/hashstr 等聚合导出按树中归属显式导入；不建立新的万能 utils 聚合包。 |
| `S/utils/__init__.py` | 工具按 dependencies、responses、middleware 与 bootstrap 分配后取消空聚合包。 |

根 `Y/__init__.py` 的无消费者 ThreadPoolExecutor 实例不进入新目录；当前包、server、CLI、脚本、镜像和 workflow 中未找到其消费。实施前再次搜索导入与部署承诺，确认可以移除。旧包路径的兼容导出只在存在明确外部调用承诺时保留，并记录消费者与退役条件；不自动为每个 rename 增加转发文件。

### 树外必须同步的装配文件

这些文件不在 `backend/yuxi/` 下，保持原位置；实施迁移时必须一起检查。

| 文件或范围 | 同步内容 |
|---|---|
| `backend/pyproject.toml`、`backend/package/pyproject.toml`、`backend/uv.lock` | 合并项目元数据、运行依赖、包资源、测试依赖与约束，移除 workspace 对本地 package 的自依赖；重新生成锁文件。保留 distribution 版本查询、Python 版本范围与显式包发现配置。 |
| `backend/package/README.md` | 核对包说明并归入唯一后端说明位置或根 README；删除旧子项目目录前明确其去向。 |
| `docker/api.Dockerfile`、`docker/api-entrypoint.sh` | COPY/安装路径改为 backend/yuxi；核对工作目录、用户权限与 package data。 |
| `docker-compose.yml`、`docker-compose.prod.yml` | 源码挂载、reload 范围、API 启动指向 `yuxi.api.main:app`；worker 指向 `yuxi.workers.main`；schema-init 指向 `yuxi.migrations.main`；healthcheck 路径同步。保持服务拓扑与依赖门禁。 |
| `backend/test`、`backend/scripts`、根 `scripts`、`.github/workflows`、`Makefile` | 导入、monkeypatch 字符串、静态源码路径、Ruff 范围、pytest pythonpath、镜像构建和测试选择器随迁移同步。仍保留现有 unit/integration/E2E 分层。 |
| 根与 backend `AGENTS.md`、`ARCHITECTURE.md`、开发与机制文档 | 实施后更新 `yuxi.services`、`yuxi.repositories` 等路径约定及源码链接。提案阶段继续以现有规则为准。 |
| `packages/yuxi-cli`、`frontend` | HTTP 协议保持不变，原则上无需随 Python 目录迁移改动；搜索是否存在路径假设后再判断。 |

内置 Skill 的 Markdown、脚本和相对资源路径属于交付资源；保留目录内容不等于自动保证镜像携带这些资源，必须从构建后的运行环境回读。数据库作业 type、handler_version、工具 slug、Agent backend_id、模型 provider ID 和公开 URL 不随纯 Python 目录迁移修改；后台作业的独立命名、schema 与 API 变更由[后台作业命名决策](../implemented/2026-10-04-background-job-naming-and-dispatch.md)拥有。

## 替代方案

- 保留技术分层并在 services/repositories 内按业务归组：迁移成本更低，同一业务仍跨多个顶层目录维护。
- `backend/src/yuxi`：可以隔离工作目录导入；本提案选择 `backend/yuxi` 减少嵌套，安装、测试与镜像统一配置导入入口。
- 一次性引入严格领域层、端口层和适配器层：缺少足够当前消费者，不采用机械套层。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 每个源文件有目标或明确退役说明 | 遗漏入口、资源文件或拆分余项 | 本提案来源映射、实际源文件 | 源目录枚举与映射覆盖检查，310 个源文件全部覆盖 | 删除 main.py 映射后检出遗漏；加入不存在来源后拒绝 | Passed |
| 迁移保留生命周期和信任边界 | 更换目录时改变事务、权限、恢复 | 源码与既有集成/E2E 测试 | 当前只执行静态检查；后续执行相关真实链路测试 | FIFO 越序、越权、失联 Run、错误结果归属 | Not run |
| 文档能构建且来源可定位 | 无效文档引用或树内来源不存在 | 本文件、文档构建 | 来源路径检查、docs build、空白检查；构建结果见验证记录 | 不存在的来源路径被覆盖检查拒绝 | Passed |

### 来源覆盖与当前范围

迁移前对 310 个源文件核对了目标或退役说明；目标树中列出的目标文件当前均已存在。来源前缀 `Y/`、`S/` 保留为历史映射，不能再作为当前目录执行命令。此次只进行静态、打包与少量配置测试；PostgreSQL、HTTP、worker 和 E2E 语义待后续变更完成后统一验证。

### 验证记录

| 检查 | 结果与范围 |
|---|---|
| 源文件映射与目标文件存在性 | Passed：迁移前 310 个源文件均有去向，当前目标文件均存在。 |
| `ruff check yuxi`、`ruff format yuxi --check`、`compileall` | Passed：迁移后的生产代码与测试均可静态解析。 |
| `pytest test/unit --collect-only -q` | Passed：2366 个单测可收集；不代表测试行为通过。 |
| Compose 边界单测 | Passed：45 个测试。 |
| 工程信任脚本及其 unittest、`git diff --check` | Passed。 |
| `uv build --offline` | Passed：源码包与 wheel 成功构建，内置 Skill 与静态配置资源存在。 |
| `docs/pnpm run build` | Passed。 |
| 后端完整 unit / integration / E2E | Not run：依用户要求，待其他调整完成后统一验证。 |

## 风险

后续调整仍可能改变已迁移的文件与符号；动态任务注册、ORM relationship、内置资源路径和镜像入口均可能使用字符串路径。目录搬迁与行为调整分开实施；提案中的拆分必须保留原事务、异常与资源释放边界。
