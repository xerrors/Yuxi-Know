# backend/yuxi/modules 结构审查报告（2026-10-11）

## 完成状态（更新于 2026-10-12）

状态对应本任务分支 `feat/modules-dead-code-cleanup`，尚未合并到 main；各阶段的提交或决策依据见下方。原始发现保留用于对照；代码行号和末尾问题计数属于 2026-10-11 审计快照。

- **【已完成】第一阶段：死代码复核与清理**，提交 `7e97aef4`；有当前消费者的入口明确保留。
- **【已完成】第二阶段：D1–D9 逐项复核与必要修复**，提交 `1432b719`；D1 原缺陷不成立，D9 原成因已更正。
- **【已完成】第三阶段：领域异常与 HTTP 协议分离**，提交 `a17c1503`。
- **【已完成】第四阶段：H1/H2 授权准备与刷新收敛**，提交 `f088bc28`；共用资源用例，按输入准备、实际请求与返回身份拆分工作；依据见[授权执行边界决策](../decisions/implemented/2026-10-12-runtime-authorization-boundaries.md)。
- **【待处理】步骤 5–17**：工具授权契约、路径边界、幂等与生命周期、业务事务归属、知识库与 Skill 收敛、跨域依赖及剩余局部问题，范围与验收见第七节。

前四阶段只闭合模式 1、模式 8 的逐项复核、D1–D9 的必要修复及 H1/H2。模式 2–7 的未完成项、H3–H9、各域中低优先级条目仍需处理；“第四阶段完成”不代表整份结构审计完成。部分修复条目只完成其中标明的范围。

`【已修复】` 表示有对应代码修复与验证；`【已清理】` 表示删除完成；`【已复核：保留】` 表示当前消费者要求保留；`【已复核：问题不成立】` 表示原缺陷被证据否定；`【部分已完成】` 与 `【待处理】` 表示仍有未闭合的范围。每阶段完成后按对应提交与证据更新下方条目。

## 方法与可信度

本报告回答一个问题：**一个新人从上到下阅读 `backend/yuxi/modules`（10 个业务域、263 个 Python 文件、约 5.4 万行）时，会在哪里被结构绊住？** 重点放在主链路上的绕路与冗余。

流程分两阶段：

1. **逐域分析**：11 个互不通气的分析者按域逐文件读完（agents 主链路/会话事件面/仓储模型/runtime、knowledge 核心/分块实现/图谱评估、extensions skills/tools+MCP、workspace+identity、五个小域），外加一个专门做跨域依赖全景的横切分析（AST 解析全部 import，34 条域级边、269 条文件级边）。
2. **独立复核**：12 个全新上下文的复核者逐条打开引用行号亲自读码、重跑 grep 验证。共 152 条候选发现，**2 条被驳回、约 25 条被修正或降级，其余确认**；复核还新发现约 27 条原分析遗漏的问题（含数个用户可见缺陷），已并入本报告。

所有死代码判断均经全仓 grep（含 test/、字符串引用、re-export、`__getattr__` 惰性导出）复核；横切分析的边计数经抽样验证零误差。分析基于 2026-10-11 工作区（`feat/agent-feedback-collection` 分支，含未提交的 feedback 相关新文件，按现状分析）。

## 总体结论

**主链路的骨架是可信的。** 逐跳核查后确认：HTTP → `inputs.py`（接收/幂等/冻结）→ `scheduler.py`（锁内建 Turn/Run/Message）→ ARQ → `runner.py`（租约+心跳）→ `execution.py`（LangGraph 流）→ `runs.py`/`messages.py`（终态收敛），每一跳都有真实职责，删掉任何一跳链路不成立；事件投影链（recorder → openai_events → event_writer → transport → SSE 相位机）同理；knowledge 摄取链（parse → chunk → embed → PG 先行/Milvus 重试）边界清晰；skills 的"授权 → 投影 → 沙盒 → 激活"链与 ARCHITECTURE.md 第 107、108、111 行不变量逐跳吻合。

问题不在链路的骨架，而在骨架周围的四类系统性模式。按对新人认知的破坏程度排序：

---

## 一、跨域系统性模式（根因级）

### 【已修复】模式 1：HTTPException 渗透全部域层（复核新增，横切最重）

原始发现（修复前）：`grep -rn "raise HTTPException" backend/yuxi/modules` 命中 **244 处、24 个文件**，遍布领域服务等模块。ARCHITECTURE.md:29/95 要求"路由只处理协议、用例归 services、路由保持薄"，但用例层直接构造 HTTP 状态码语义，路由只能透传——这也是下文幂等回执、Session 授权等模式无法沉淀为域内共享机制的结构性原因之一（五份幂等拷贝各自绑定 409+中文 detail 的 HTTP 表达）。同域内已有正确示范（`agents/services/password_login.py` 的领域异常模式、`identity/services/administration.py` 的 service 事务 Owner），但两种哲学并存，新人无从判断该学哪一种。

修复结果：全部 244 个抛出点及相应捕获已迁移为领域异常；API 适配器保留原状态码、消息与业务 code，定时、预览、工具和 worker 按领域契约消费。领域异常不携带 HTTP 属性。

### 【待处理】模式 2：并发敏感惯用法五份实现，无收敛点

- **【待处理】** **幂等回执四件套**（校验键 → sha256 意图指纹 → 拒绝异意图重放 → accepted）：agents 域内三份（`inputs.py:397` / `turns.py:498` / `threads.py:355`，细节已漂移：`threads.py:363` 的 `json.dumps` 缺 `default=str`、`_accepted` 返回形状三处不同），并泄漏到 `schedules/service.py:229` 与 `workspace/services/projects.py:38`，共五份。核心语义五份一致（复核确认无有害漂移），唯一分歧：schedules 对已软删任务允许同 request_id 重放、workspace 对已删 Project 返回 409。
- **【待处理】** **"建 Run + 绑输入消息 + set_current" 事务模式**在 4 处复制（`scheduler.py:59`、`runs.py:206`、`turns.py:107`、`cooperation.py:530`），每处重复拼装 create_run 的 15-17 个同名参数；resume Message 的同形状构造另有两份（`turns.py:87` / `cooperation.py:518`，复核新增）。
- **【待处理】** **"幂等预检 → 锁 → 锁后复查" 调用点级样板**在 agents 全部入口重复约 13 处（复核新增）——这不是抽 helper 能解决的，是入口协议没有抽象表达。
- **【待处理】** **终态收敛序列三份**：`_finish_run`（runner.py:428）与 `_finish_user_cancel`（:466）之外，`process_agent_run` 的 committed 路径（:815-838）还有第三份内联副本，且内联版独有终态一致性断言（复核新增）。

### 【待处理】模式 3：分层方向倒置与跨域循环

文件级真实 import 环仅 2 个（均在 options 聚合家族），但域级概念环遍布：

- **【待处理】** **repositories 反向依赖 services**：`agents/repositories/input.py:14`、`feedback.py:10`、`definitions.py:364`（函数内引真实用例逻辑，构成实质倒置）；`knowledge/repositories/bases.py:8` 同型。未成环仅因被依赖模块恰是纯叶子。
- **【待处理】** **靠函数内延迟 import 维持的环**：agents 域 14 处（cooperation ↔ inputs/turns/threads 双向）；knowledge 域 graphs ↔ implementations/milvus.py；skills 包内 shared ↔ content，skills ↔ tools 双向。新人无法区分"解环"与"惰性加载"——复核确认 agents 域 10+ 处延迟 import 中只有 1 处是真实解环。
- **【待处理】** **modules → 进程适配层反向依赖**：`background_jobs/registry.py:46` import bootstrap 的 JOB_DEFINITIONS（纯字符串表，可直接放 registry）；`system/readiness.py:20`、`agents/services/transport.py:11` import `yuxi.workers.health` 的健康键常量；另 3 处 TYPE_CHECKING 引用。
- **【待处理】** **平级域互相穿透**：`background_jobs/dispatch.py:8` 取 agents 域的 `get_arq_pool`（本质是 infrastructure 级 ARQ 池访问器）；`identity/repositories/users.py:112-115` 直接 DELETE schedules 域的 ORM 表（软删使 DB 级联永不触发，应用层删除确属必要，但删除策略被两域共同拥有）；`system/repositories/dashboard.py:10-14` 直接 select agents ORM 并跨域构造 AgentRepository。

### 【待处理】模式 4：下划线私有属性构成跨域公共契约

`BaseContext` 的真实运行时契约由 **12 个未声明的动态私有属性**构成，散布 6 个文件：`_skill_runtime_snapshot`（skills→agents 3 域消费，字符串 key 取裸 dict）、`_mcp_tool_servers`/`_registered_builtin_tool_names`（tools/runtime 写、skills 中间件防御性重写、authorization 读——**`getattr` 默认空值意味着属性缺失时工具检查静默放行（fail-open）**，复核加重的加重项）、`_enabled_mcps`（**命名与语义相反，存的是 disabled_tools 集合**，复核新增）。测试直接手工构造这些属性，证明它们已是事实上的公开契约。

### 【待处理】模式 5：同名异义与命名失真

- **【待处理】** `KnowledgeBase` 同名三义（抽象执行器 / ORM 表 / 声明式基类）；`MilvusGraphService` 主体是 Neo4j Cypher；`modules/models` 域名与全仓 "models=ORM" 惯例撞车（ORM 被迫叫 tables.py，bootstrap 注册表 18 项里它是唯一例外）；`catalog`/`runtime` 在 extensions 两个子域与 agents.runtime 三方撞名，工具门控实现住在 skills/runtime.py 却被 tools/runtime.py 反向调用；`skills/draft.py` 是"安装暂存"不是"编辑草稿"；`events.py` 是读取端而 `event_writer.py` 才写 Redis；`messages.py` docstring 说"读取"但 2/3 是 Run 结算写路径；`skills` 域 `revision` 一词三种互不兼容语义（整目录哈希 / 单文件 sha256 / 根文件 SKILL.md sha256），router 层统一 409 不区分。
- **【待处理】** 16 个 repository 与 services 存在 4 对同名文件（definitions/public_items/references/state）；`repositories/state.py` 是唯一不接收 AsyncSession 的"仓储"（LangGraph checkpoint 包装）。

### 【待处理】模式 6：路径与校验规则多处漂移

- **【待处理】** 沙盒绝对路径规整三处实现宽严不一（`tool_approval.py:56` 拒 `..`/`\\`/`://`，`sandbox/backend.py:96` 仅拒 `..`，`sandbox/paths.py:47` 全拒）。
- **【待处理】** workspace 路径校验 4 处各自实现（`://` 只有两处检查；子目录名校验三种机制三种错误类型；ELOOP 被翻译成两种异常）。
- **【待处理】** **"用户可见路径" allowlist 三处手写且已漂移**（复核修正）：`present_artifacts.py` 缺 `..` 检查、`agents/services/artifacts.py` 缺 workdir 空值守卫、异常类型各异——`paths.py:88` 的 `is_runtime_path()` 已存在但无人复用。

### 【部分已完成】模式 7：同一数据/契约的多份表示

- **【部分已完成】** chunk 被 4 类字典形态建模（摄取平铺 / PG 记录 / 检索三元组 4 处手写副本 / schema 转换），摄取侧 `filename`/`source` 字段无任何读取者——而检索侧 `metadata.source` 硬编码 `"未知来源"`（见下文缺陷 D1），来源未接通的原结论已由 D1 复核否定；四类表示的收敛仍待处理。
- **【待处理】** 同一 KnowledgeFile 行共 5 种 dict 形状；**Milvus collection schema、索引参数（IVF_FLAT nlist=1024、SPARSE_INVERTED_INDEX）、embedding 函数装配在 implementations/milvus.py 与 graphs/milvus_graph_vector_store.py 逐字两份**（复核新增，数据层契约一旦单侧修改即静默分叉）。
- **【部分已完成】** KB 统计数字一份聚合 + 两条交付路径（列表页读持久化快照、详情页读实时聚合），后台失败收敛绕过统计刷新的漂移点已修复（D4）；双交付路径本身未收敛。
- **【待处理】** "信号量 + to_thread 卸载"约 40 行并发原语在 knowledge 两个文件逐字两份。
- **【待处理】** advisory lock 四种调用姿势混用同一键空间（`hashtextextended` / 32 位 `hashtext` / 裸常量 / DDL与应用镜像常量），裸键至少 6 处无注册表。

### 【已完成复核与清理】模式 8：死代码与"仅测试供养"的生产代码

逐项复核结果如下；原报告的“零引用”不能直接作为删除结论，测试与正式扩展消费者也计入保留依据。

- **【已清理】`services/commands.py`**：整文件及孤立测试删除。
- **【已清理】`get_run_langfuse_link`、`get_active_run_by_runtime_scope_for_user`、`get_latest_for_thread`**：死服务与查询删除。
- **【已清理】`get_allowed_agent_access_levels`、`normalize_agent_share_config`**：两个无消费者策略函数删除。
- **【已清理】`SessionRepository.create_session`**：无消费者创建入口及孤立测试删除。
- **【已清理】Agent 域五个孤立 ORM `to_dict`（含 ToolCall 的传递死亡）**；**【已复核：保留】`Agent.to_dict`、`AgentRun.to_dict`**：前者有生产消费者，后者有测试消费者。
- **【已清理】knowledge `list_file_tree` 三层链与专用遍历辅助**；**【已复核：保留】下载入口使用的原文件路径辅助**。
- **【已清理】knowledge repository 的 `delete_by_kb_id`、`mark_graph_indexed`、`get_all`、`list_by_file_ids`、`list_by_kb_id_after`**；**【已复核：保留】知识文件存在性查询**。
- **【已清理】`chunk_file`、`infer_heading_level`、`get_whitelist_info`、`GraphExtractorFactory.supported_types`**。
- **【已清理】identity repository 的 `list_users`、`get_by_phone`、`get_admin_count_in_department`、`soft_delete`**；**【已复核：保留】`AuthUtils.generate_api_key`、`decode_token`**：真实测试资源创建与登录校验仍消费这些入口。
- **【已清理】`tools/utils.py`**：整文件删除，生产工具信息入口由 catalog 拥有。
- **【已清理】MCP 的 `get_tools_from_all_servers`、`get_servers_config`**；**【已复核：保留】单服务器工具加载入口**。
- **【已清理】`SENSITIVE_BACKEND_TOOLS`、`MILVUS_AVAILABLE` 恒真守卫、`SOURCE_CITE_PROMPT`**。
- **【已清理】`middlewares/context.py`**：两个死函数、文件及导出删除。
- **【已清理】模型适配层 `resolve_model_spec`、`is_full`、`embed_state`、同步 `compute_score` 及未消费的包级导出分支**；**【已复核：保留】模型包的 `select_model`**。
- **【已清理】transport 的 `normalize_after_seq`、`get_last_run_stream_seq`、专用序号校验及死导出**；**【已复核：保留】单事件 Redis 写入包装**。
- **【已清理】workspace `__init__.py` 无消费者导出**。
- **【已复核：保留】`fallback=`、`list_top_level_runs_after_sequence` 等仅测试引用入口**：实际测试仍依赖这些契约，未按“仅测试引用”批量删除。

完成依据：`7e97aef4` 与 `docs/develop-guides/decisions/implemented/2026-10-12-dead-code-cleanup.md`。

---

## 二、高优先级发现（影响正确性、性能或新人判断方向）

### 【已修复】H1. 授权中间件每个模型步骤重复 3-4 次全量重授权【性能+结构，复核确认高并加大量级】

`middlewares/authorization.py` 的 `refresh_execution_authorization`（:79-143）无任何缓存/短路：每次开新 DB 会话约 8-12 次往返（User、Run、Agent 可见性 ×2、资源配置、MCP、Skills 行锁查询），随后 `sync_agent_context_skills` 再开第二个会话做 `pg_advisory_xact_lock` + 行锁 + 目录扫描重建投影。LangGraph（langchain 1.3.17，容器内核实）的 `before_model`、`wrap_model_call`、`after_model` 之间**不存在任何授权状态变化事件**，却在同一窗口连做两遍，`after_model` 第三遍，每次工具调用第四遍；摘要路径 `_authorize_summary_request` 再加一轮。单个模型步实际成本约 **10-15 次 DB 往返 + 2-3 次文件系统扫描**。构图期（graph.py:94）已 sync 一次。重授权的 fail-closed 设计本身正确，问题纯粹是同一无事件窗口内的重复次数与每次的重量。

完成依据：输入准备仍读取当前资源，实际模型、重试、摘要与工具调用前重新授权并同步投影；返回阶段仅复查持久身份，先于审批等待点。普通无重试模型轮次从三次投影同步降为一次，真实 PG/文件测量为来源与目标哈希扫描 **6 → 2 次**、Agent 可见性 SQL **6 → 3 次**；构图同步另计。仍保留两次资源读取与三次身份检查，未引入授权缓存。原记录“边界之间不存在授权状态变化事件”的前提已更正：MCP 发现和模型等待等 await 期间可以发生外部撤权，因此输入与实际请求的检查分别保留。验证及范围见[执行边界决策](../decisions/implemented/2026-10-12-runtime-authorization-boundaries.md)。

### 【已修复】H2. 准备与刷新是两份几乎同构的平行实现（复核新增）

`prepare_agent_runtime_context`（runtime/context.py:485-536）与 `refresh_execution_authorization`（authorization.py:79-143）各自实现"读用户 → normalize 配置 → resolve_runtime_skills → 写回 `_skill_runtime_snapshot`/`_capability_limited`"全流程，互不调用、过滤规则各自维护（如准备路径不校验 Run/Thread 归属而刷新路径校验）。授权刷新每次执行的正是与准备流程漂移风险最高的复制逻辑——这是 H1 的结构根因。

完成依据：准备与刷新均调用 `refresh_agent_context_resources`，统一原始选择、资源规范化、Skill 快照、专属根正文保留与能力受限判断。刷新将同一事务已授权的 Agent 传入 Skill 解析，消除重复可见性查询。首次准备与 Run/Thread 执行刷新保留各自身份入口；资源撤权及重新授权恢复、专属根正文冻结与共享正文更新均通过真实 PG/文件回读验证。

### 【待处理】H3. repositories/definitions.py 承担 service 职责，路由绕过 services 直采【复核确认高】

`repositories/definitions.py` 导出整个 Agent 治理策略库（:41-78 权限函数、:512-562 含越权拒绝的配置合并、:463-509 调 runtime backend 组装 DTO），`api/routers/agents/management.py:12-17` 绕过 services 直接 import 这些策略函数，:126/:136 还直接调 `repo.ensure_default_agent()`（内部 commit）。同一"配置越权校验"创建路径在 service 做（services/definitions.py:20-27）、更新路径却在 repository 做（:363-371）。复核补充：`api/routers/identity/users.py:276` 同样直接调 `AgentEnvRepository(db).upsert()`。

### 【待处理】H4. sessions.py 名不副实，messages 表无归属仓储【复核确认高】

`repositories/sessions.py`（803 行）混合 4 类职责：Session 持久化、Message/ToolCall 写 API（:226-339）、memory 历史协议（:574-712）、字节预算响应装配（:729-803，service 层职责）。Message 表的写入分散在 **7 个 repository 文件**（sessions、input、model_audit、tool_audit、runs、public_items、references），读取另有 turn.py 与 system/dashboard。新人问"消息在哪写、在哪改可见性"必须跨 8 个文件。

### 【待处理】H5. identity 域大量用例没有 service 事务 Owner【复核确认高，并扩大】

API Key 创建整个用例在 `api/routers/identity/users.py:150-200` 路由内（derive/commit/异常翻译），而 CLI 同构用例却由 `services/cli_auth.py:151-193` 拥有事务——同一"创建派生 API Key"两个 Owner；api_keys repository 的 update/delete 又自带 commit。部门 update、UserConfig.save 同型。**复核补充：`auth.py` 的用户 CRUD 全套（create_user :444-533、update_user、delete_user、update_profile、upload_avatar）同样整体无 service Owner**，规模大于原发现点名之和。对照域内 `administration.py`（正确示范）风格分裂。

### 【待处理】H6. tools/runtime 与 skills 中间件的私有属性契约含 fail-open 缺口【复核确认高并加重】

见模式 4。`authorization.py:73,76` 的 `getattr(context, "_mcp_tool_servers", {})` 默认值意味着任何绕过 `resolve_configured_runtime_tools` 构造 context 的路径，工具检查会**静默放行**而非拒绝。生产路径因初始化无条件执行而当前安全，但契约没有结构保证。

### 【待处理】H7. skills/shared.py 是 633 行、6 类职责的依赖中心【复核确认高】

共享 Skill 用例、内置同步、运行时锁、权限原语、依赖校验、读取入口、路径工具全部在一个文件，且是包内依赖中心（与其他 15 个文件互相纠缠）；包内唯一没有模块 docstring 的文件之一。"内置 Skill 同步"在 `builtin/` 目录里找不到——在 shared.py 里。

### 【待处理】H8. knowledge 图层复制了实现层的存储装配知识【复核确认高并扩展】

40 行并发原语逐字两份（模式 7）之外，复核新增：`_get_embedding_function` 与 Milvus collection schema/索引参数在 `implementations/milvus.py` 与 `graphs/milvus_graph_vector_store.py` 各一份——这是比信号量副本更接近数据层的漂移风险。伴随 `MilvusGraphVectorStore` 构造含真实 RPC（`db.list_database`）却在每次图检索时随意 new。

### 【待处理】H9. 幂等回执五份 + 预检样板 13 处（模式 2 的主实例）【agents 内部三份经复核降为中：漂移是潜在的而非现行 bug；跨域泄漏两份维持中】

### 【已清理】H10. `services/commands.py` 整文件死代码【复核确认高】

清理结果：文件与孤立测试已删除。原始发现：整文件实现 Channel slash command 解析，全仓（后端+前端+docs）零生产引用，仅一个孤立单测供养（当日另一份审计文档也已标记该测试孤立）。

### 【已清理】H11. knowledge `list_file_tree` 三层整链死代码【复核确认高】

清理结果：三层链与专用遍历辅助已删除，下载辅助保留。原始发现：base 抽象 → manager 转发 → ReadOnlyConnectors 拒绝实现，整条能力链零调用方；前端文件树实际走 `list_document_files`。连带 base.py:521-599 整簇私有辅助死亡。

---

## 三、复核发现的用户可见缺陷（原分析遗漏）

以下保留原始发现，并附逐项复核与修复结果；D1 原缺陷不成立，D9 原成因更正。

- **【已复核：问题不成立】D1. Milvus 知识库的 Agent 引用标题恒为"未知来源"**：`implementations/milvus.py:875,1274` 检索侧 `metadata.source` 硬编码占位符，`agents/services/references.py:309` 的 truthy 判断短路了 file_id 兜底；而摄取侧 dispatcher 记录携带真实 `filename` 却无人消费——两半数据恰好错开。dify/notion 路径正常。 **复核结论：向量、关键词、混合及图谱结果在返回前已有 PostgreSQL 文件名补齐；原缺陷不成立，检索装配到引用标题的回归测试验证现有行为。**
- **【已修复】D2. Redis 故障被伪装成配置错误**：`providers/cache.py:104-116` 模型缓存 Redis 异常时返回 `{}` 且**无 PG 回源**（rebuild 仅在启动与管理员保存时触发），故障期间所有模型解析以"未找到模型 'xxx'。可用聊天模型 (0): []"的 ValueError 暴露——基础设施故障呈现为用户配置错误，且空列表误导排查。 **修复结果：Redis 读取失败、快照缺失或非法明确抛出基础设施错误；有效空快照仍合法，未新增 PostgreSQL 回源。**
- **【已修复】D3. 知识库重名是 check-then-create 竞态**：`manager.py:498` 先查后建，`models.py:32` 的 name 列**无 unique 约束**，并发创建同名知识库可双双穿透，无数据库兜底。 **修复结果：活动知识库名称增加 lower(name) 部分唯一索引及 knowledge 3→4 原子迁移，并发创建/重命名冲突返回 409；存量重名阻止升级且保留数据。**
- **【已修复】D4. 后台失败绕过统计刷新**：`services/background_jobs.py:36` → `files.py:836-858` 直接置错误态不经 `_run_with_stats_refresh`，列表页持久化统计与详情页实时聚合在此路径上漂移。 **修复结果：Job、文件错误态与受影响知识库的持久统计在同一事务收敛，沿用 KB→File 锁序；详情短期缓存仍按 TTL 过期。**
- **【已修复】D5. 内置 Skill 的 admin"可见但不可管理"语义冲突**：`repository.py:33` 让 admin 在管理页看到可管理卡片，`shared.py:493` `user_can_manage_skill` 却只认 superadmin——所有管理操作会被拒，UI 与权限规则互相矛盾。 **修复结果：列表、响应与管理用例消费同一权限解析；有效 superadmin 管理内置 Skill，admin 只读取符合可读规则的内置项。**
- **【已修复】D6. web_search 无 provider 时静默缺席**：无凭据时直接 return 不注册、无任何日志，违反"降级必须结构化、可观察"（AGENTS.md）。 **修复结果：缺少凭据或注册失败产生结构化降级日志，能力缺席有可观察原因。**
- **【已修复】D7. MCP 两条建连路径失败语义相反**：Agent 运行时吞异常返回空工具列表，管理 UI 显式报错——同一台坏服务器两个视图给出相反信号。 **修复结果：MCP 建连与工具发现异常传播为运行失败，正常零工具结果仍合法；配置装配与 Skill 中间件不再吞异常。**
- **【已修复】D8. `delete_file_graph` 在异步上下文走同步 property**：首次构造会在事件循环内做 Milvus 网络 IO（`milvus_graph_service.py:760`），恰是异步版 `get_graph_vector_store()` 要防的阻塞。 **修复结果：通过异步 get_graph_vector_store() 初始化入口取得客户端，同步构造在线程执行。**
- **【已修复（原成因已更正）】D9. `UserRepository._session()` 双模式陷阱**：`db_session=None` 时自建会话而 save/create 只 flush 不 commit——当前所有写调用方恰好都注入了 db，未来无参写调用会静默丢数据。 **复核更正与修复结果：PostgresManager 的自建会话上下文本身会 commit；实际风险是独立 save 的 detached 实体与会话不匹配。所有用户写操作现要求注入调用方事务，只 flush、由调用方提交或回滚；独立读取继续支持。**

---

## 四、中优先级发现（明显绕路/重复，影响可控）

**agents 域**

- **【待处理】** Session 授权决策三处实现（`threads.require_thread` 规范版 / `attachments._require_user_session` / `compression` 内联，谓词与文案各异），8+ 文件复用规范版说明另两处是平行实现。
- **【待处理】** `feedback.py` 内联重写 Turn/Run 作用域查询（:95-108，谓词与 `get_for_scope` 一致），同类场景其余 15 处都走 repository。
- **【待处理】** 工具错误文案两层独立派生且默认值不同（审计"Tool 执行失败"×3 处 vs 公开"工具执行失败"），更深层：工具输出在审计层（JSON 字符串化）与公开层（结构化透传）**序列化规则分叉**，与"工具结果在该入口规整一次"的意图有张力。
- **【待处理】** `repositories/` 事务归属两种模型并存（12 处自行 commit vs 13 文件绑定调用方事务）；`commit: bool = True` 默认值当前零使用（三个调用点都显式传 False）——未引爆的脚枪；`mark_thread_viewed`/`ensure_default_agent` 在用例/路由流程中真实内部提交。
- **【待处理】** repositories 之间内联互构（`definitions.py:350,416` 构造 UserRepository、两个 audit repository 各自构造 AgentRunRepository、sessions/public_items 方法内构造他仓储），锁序契约无静态表达。
- **【待处理】** cooperation 与核心生命周期双向依赖、14 处延迟 import；`_stream_agent_execution`（execution.py:446-651）约 200 行混合事件路由/steer 循环/checkpoint 提取/收尾，是本域可读性最差单点。
- **【待处理】** `middlewares/summary.py` sync/async 两份 65 行压缩流程（复核否定了"框架固有权衡"辩护：其他中间件同步份只有 3-6 行；且 sync 版生产不可达、缺授权调用）；三个近似摘要函数仅一词之差。
- **【待处理】** `sandbox/provider.py` 绕过 AgentEnvRepository 裸 psycopg 读 agent_envs（同步上下文约束可辩护，但同表两条读取路径 + 连接串规整两份属实）。
- **【待处理】** `Workspace` 与 `ProvisionerSandboxBackend` 平行实现同名 `*_authorized_*` 五组契约，签名各异、无共享协议；`extensions/tools/knowledge/tools.py:262` 直接实例化他域 backend。
- **【待处理】** `BaseContext` 12 个动态私有属性（模式 4）。
- **【待处理】** `run_type` 校验后残留不可达 else；`stream_agent_chat/resume` 纯透传双胞胎；连续两次空 commit；用户加载四种写法两种过滤口径（inputs.py:93 **与 ：343** 均无 is_deleted 过滤）；投递 ARQ 两条惯例（messages.py:580 绕过 deliver）；游标分页骨架 4 份复制。
- **【待处理】** events/messages 命名错位（"events.py 只读、event_writer 才写 Redis"这一误解正是任务下发时分析者自己踩的坑——命名误导的直接证据）。

**knowledge 域**

- **【待处理】** "删除知识库"的软删除事实由 `KnowledgeFileRepository` 拥有（files.py:894-945 锁 KB 行写 tombstone），`KnowledgeBaseRepository.delete` 反是仅清理任务用的硬删除。
- **【待处理】** manager.py（1330 行"上帝门面"）：真正的用例流程住在根目录而非 services/（与 ARCHITECTURE.md:95 表述错位）；约 9 个纯转发方法 + 6 处重复的两行惯用法；`manager.aquery -> str` 注解与实际 `list[dict]` 返回不符（4 个生产调用方）。
- **【待处理】** 文件状态词表散落（FileStatus 常量 7 值 vs 仓储裸写 9 值，"done" 仅文件夹写入者却作 indexed 别名被读）；状态筛选两条链路映射不同——复核确认**当前无用户可见分叉**（搜索链路无人传 status），但属遗留兼容的潜在分叉。
- **【待处理】** 三个 abstract 方法唯一真实实现只读 PG/MinIO 不触碰 Milvus（抽象点过时）；同一 ORM 行 5 种表示。
- **【待处理】** 授权落点复核确认可辩护（ARCHITECTURE.md:42 明文"可见范围解析由 knowledge service 拥有"，未发现绕过路径），残余问题是与第 117 行跨域概括的措辞张力。
- **【部分已完成】** 重名检查全表扫描与读取 `_initialized` 的结构问题仍待处理；**【已修复】缺 unique 约束（D3）**。
- **【待处理】** 大 KB 删除是重事务 + N+1（每文件 2 次往返、逐行 FOR UPDATE，复核新增）。
- **【待处理】** evaluation 四个作业钩子绕过 repository 直改 ORM（同域知识文件侧钩子是委托风格）；LLM 抽取器每 chunk 重建模型实例并打 INFO 日志（万级 chunk 即万次构造）；评估筛选 service 层全量扫描分页。
- **【待处理】** chunking：semantic 预设的 `embed_model_id` 隐式跨层契约（缺参时 ERROR 日志后静默退化为长度切分）；`get_default_chunk_parser_config` 恒返回 `{}` 名实不符；chunking 包是空 facade、移植/自有边界无标注（自有胶水 presets.py 混在移植子树内、移植 parsers 反向依赖自有 source_spans）；检索参数默认值两套（面板 0.0/50 vs 运行时回退 0.2/recall_top_k，仅存量 KB 触发且面板显示与运行时脱节）。
- **【部分已完成】** graphs：`build_graph_payload` 去重分支与 utils 层的用例归属仍待处理；**【已修复】领域 HTTPException**（模式 1）；**【已清理】`supported_types`、`get_whitelist_info` 与确认无消费者的导出**（模式 8）。

**extensions 域**

- **【待处理】** skills：shared↔content 循环、skills↔tools 双向依赖（第二处环，复核新增）；`_skill_runtime_snapshot` 无类型 dict 契约；ResolvedSkill 来源三重表述 + 方向相反的双布尔；投影刷新"按 slug 删除却按 uid 全量重建"的粒度不对称（吞异常侧有文档化补偿机制，属有意取舍）；两套目录哈希算法同写 `content_hash` 列且列注释失实；远程安装双管线；"临时目录+原子 rename"五处手写回滚语义各异；ADMIN_ROLES 四处定义。
- **【部分已完成】** tools：**【已清理】`tools/utils.py` 整文件**（活版本在 catalog）；debug/ 空壳目录以"自动注册"名义被导入；**【已完成复核与清理】MCP 无消费入口与导出**（单服务器工具加载有当前消费者，保留）；web_search 绕过 @tool 直改注册表私有全局（且 `get_all_tool_instances()` 返回可变全局活引用——复核新增的根因）；`get_common_kb_tools` 及 KB 工具包级导出零消费；同包两套 sandbox scope 解析回退语义不同；catalog 缓存版/现算版两套读模型；`mark_for_improvement` 的 category="runtime" 无任何后端过滤、前端将裸渲染标签。
- **【待处理】** mcp：runtime docstring 声称的参数不存在；"Global Cache & State"注释段无实体；同一 warning 文案三处。

**workspace + identity 域**

- **【部分已完成】** workspace↔agents 双向依赖（repository 级互指，复核补充 viewer.py:15 漏列）；**【已清理】workspace 顶层 `__init__.py` 零消费导出**；errors.py 只 re-export infrastructure 异常而领域异常住在 repository；identity 三层包形态（有无 `__init__.py`）与 agents 域不一致。
- **【部分已完成】** identity/oidc.py：**【已修复】6 处领域 HTTPException**（模式 1）；service 平铺顶层及 import 时固化配置单例仍待处理（复核修正：services/oidc.py 拥有事务与登录编排，剩余问题是用例归属 :95；异常风格已统一）。
- **【待处理】** 登录响应三处手写、avatar 归一化分歧（影响面：OIDC 登录且已设头像用户，复核降为中）。
- **【待处理】** `verify_api_key` 内联重写 `APIKey.is_valid()` 三条判断（Public API 安全路径）。
- **【待处理】** 三种跨层路径之外存在第四种表示（UserWorkspace scope 绝对路径），DB 相对路径→Workdir scope→workspace scope→runtime 虚拟路径四次形态转换；Workdir 15 个方法 12 个单行转发而个人工作区服务完全绕过它；`relative_path`/`root_path`/`workdir_path` 同值三名。
- **【待处理】** 路径/子目录名校验 4-5 处漂移（模式 6）；files.py/viewer.py 重复异常翻译 18 处、条目组装与二次排序各两份。
- **【待处理】** OIDC state/login_code 存进程内存 dict（当前单 uvicorn 进程，扩多 worker 即静默失效）；`exchange_code_for_token` 方法名遮蔽导入函数。
- **【待处理】** resource_ownership.py 让基础身份域反向编排三个资源域（方向问题，非明文违规）。

**五个小域 + 跨域**

- **【待处理】** `modules/models` 域名撞车（复核降为中：ARCHITECTURE.md:45 有文字区分，纯认知负担）。
- **【待处理】** 健康键契约住在 `workers/health.py`（含可执行 main），业务域反向 import；`create_arq_pool` 访问器住在 agents 业务域迫使 background_jobs 反向依赖；JOB_DEFINITIONS 纯字符串表住在 bootstrap。
- **【待处理】** system 域两套分层并存；options 单文件混杂 + 与 documents/extensions 两个真实文件级 import 环（Option 契约放业务域是根因）；DashboardService 9 个方法 8 个转发（唯一价值是约定挂点）。
- **【待处理】** embed 的 encode/aencode 两份 HTTP 主体；三域"PG 为源 Redis 为缓存"样板零共享（失效策略差异是有意的，重复的是容错样板）；`select_model`/`load_chat_model` 双入口的适用规则只能靠查 consumer 归纳；适配器 `raise Exception(err)` 吞掉异常类型。
- **【已清理】** 模型适配层死代码群（resolve_model_spec/is_full/embed_state/同步 compute_score/未消费的包级惰性导出分支）；有消费者的 select_model 保留。
- **【待处理】** documents 域硬编码 `"siliconflow-cn"` 供应商 ID 跨域直查（复核新增）。
- **【待处理】** 幂等回执泄漏 schedules/workspace（模式 2）；advisory lock 键空间无约定；`_preprocessed_map` 等带内魔法键跨 router/utils 传递。
- **【待处理】** 分层模式不一致：knowledge/services 有 `__init__.py` 而 agents/workspace/identity 的 services/ 没有；agents 域内自身也不一致。

---

## 五、低优先级（局部瑕疵，修复廉价）

- **【已完成复核与清理】死导出与死常量**：以模式 8 的逐项结论为准，有消费者的入口明确保留。
- **【待处理】`ATTACHMENT_ALLOWED_EXTENSIONS` 恒空却暴露进 API limits**。
- **【待处理】`commit_agent_definition` 之外的零星死参数**。
- **【待处理】`_get_file_meta` 纯别名与 `del refresh`**。
- **【已清理】`MILVUS_AVAILABLE` 恒真守卫、`SOURCE_CITE_PROMPT`**。
- **【待处理】`base.py` 类型注解失真与 `manager.aquery` 注解错误**。
- **【待处理】`_enabled_mcps` 命名反义**。
- **【待处理】promote_input 缺锁前检查**：不对称是否有意仍需核对。
- **【待处理】`get_pending_steer` 丢弃返回值**。
- **【已清理】`SessionRepository.create_session` 与其返回值自校验**。
- **【待处理】scheduler 之外三处裸 advisory 常量**。
- **【待处理】OIDC 两个近似重复函数**。
- **【已复核：保留】tool_result 排除语义**：有测试 fixture 专门写入验证，属于遗留数据防御。
- **【待处理】advisory lock 超管常量镜像的绑定注释**：镜像为有意设计，注释缺口仍在。

---

## 六、诚实记录：被驳回与被修正的发现

复核驳回 2 条、实质性修正约 25 条。重要的修正：

| 原发现 | 复核结论 |
|---|---|
| `commit_agent_definition` 的 `user` 参数从未使用 | **不属实**：`definitions.py:73` 的 `refresh_binding` 分支真实使用 |
| `runtime/__init__.py` 导出无消费者 | **不属实**：`docs/agents/agent-backend-development.md:63`、`agents-config.md:102` 以 import 形式消费，是文档化的扩展 API |
| messages.py 三处调用触发隐式提交 | **不属实**：三处均显式传 `commit=False`，缺陷现不存在（默认 `True` 是未引爆的脚枪） |
| 状态筛选两链路用户可见分叉（高） | 降为低：搜索链路无任何调用方传 status，差异只影响存量数据 |
| knowledge 授权落点违反架构（中） | 降为低：ARCHITECTURE.md:42 域内条款支持现落点，未发现绕过路径 |
| `_turn_event` 与 `adapter._event` 拼同一信封（中） | 修正：event_id 派生与载荷有意不同（读端确定性重放 ID），可合并的仅骨架 |
| tool_result 是幽灵值 | 修正：4 处测试 fixture 专门写入验证排除行为，models 列注释列其为合法值 |
| middlewares/context.py 死代码（高） | 降为低；**【已清理】**两个函数、文件与导出已删除 |
| catalog/runtime 三方撞名（高） | 降为中：各自命名空间无冲突，代价是门控语义分散 |
| identity/oidc.py"services/oidc.py 是薄壳" | 修正：后者是事务 Owner 与登录编排，违反的是用例归属与风格分裂 |
| skills 路径解析 4 处重复（中） | 降为低：校验语义 Owner 唯一（`validated_shared_skill_parts`），重复仅一行 joinpath 包装 |
| tools/runtime 工具名三处硬编码 | 修正：tools/runtime.py 用 `.name` 属性引用（正确写法），字符串硬编码实为 2 处 |
| 幂等回执 threads 缺 `default=str` 是现行 bug（高） | 降为中：现调用只传字符串，属潜在漂移；已发生的漂移在 `_accepted` 返回形状 |
| repository 反向 import"违反 ARCHITECTURE.md" | 修正：文档无依赖方向明文；definitions.py:364 一处构成实质用例倒置，另两处是契约放错层 |

方法可信度抽查：横切分析的 34 条域级边中抽样 3 条人工验证，import 计数零误差。

---

## 七、实施步骤与验收范围

前四步保留完成状态；后续按安全边界、并发与事务、业务分层、数据契约、依赖与命名的顺序推进。下面是待实施范围，具体修改先在当前源码和消费者处复核，再按 [Spec Loop](../spec-loop.md) 确认方案；原审计快照中的行号、数量与判断不直接充当新实现的依据。

| Step | 状态 | 范围 |
|---|---|---|
| 1 | 已完成 | 模式 8：确认消费者后清理死代码，`7e97aef4` |
| 2 | 已完成 | D1–D9：复核与必要修复，`1432b719`；D1 不成立，D9 成因更正 |
| 3 | 已完成 | 模式 1：领域异常与 HTTP 表达分离，`a17c1503` |
| 4 | 已完成 | H1/H2：资源准备与刷新共用、投影成本收敛，`f088bc28` |
| 5 | 待处理 | H6 / 模式 4：显式运行契约与工具授权拒绝边界 |
| 6 | 待处理 | 模式 6：路径、文件访问与产物发布边界 |
| 7 | 待处理 | H9 / 模式 2：幂等回执与锁前锁后复查 |
| 8 | 待处理 | 模式 2：Run 创建、输入绑定与等待恢复 |
| 9 | 待处理 | 模式 2：终态收敛、事件发布与运行恢复 |
| 10 | 待处理 | H3/H4：Agent 用例分层与消息持久化职责 |
| 11 | 待处理 | H5：身份用例事务归属与登录契约 |
| 12 | 待处理 | H8 / 模式 7：知识存储装配与数据表示契约 |
| 13 | 待处理 | knowledge：用例、状态、统计与处理性能 |
| 14 | 待处理 | H7：Skill 用例与工具注册边界 |
| 15 | 待处理 | 模式 3：跨域依赖、进程适配与共享技术职责 |
| 16 | 待处理 | 模式 5：命名、文档及剩余局部清理 |
| 17 | 待处理 | 整份审计逐项闭合与交付复核 |

### Step 5：【待处理】显式运行契约，先补 H6 的拒绝边界

覆盖 H6、模式 4，以及 agents/extensions 中重复列出的动态私有属性问题。声明 Context 的 Skill 快照、工具来源、注册工具和 MCP 禁用工具等实际运行契约，明确初始化与消费位置；缺失必要装配时拒绝执行。`_enabled_mcps` 的禁用语义命名在此处一起处理，避免后续再迁移同一消费者。H1/H2 保留的输入、实际请求和返回身份检查继续有效。

同时复核 summary 的 sync/async 两份压缩流程和三个近似摘要函数：按正式装配、扩展及测试消费者决定同步入口的去留，保留的流程共用压缩规则和相应授权语义，自动与主动摘要保留各自入口结果。

验收：用独立/替代 Context 构造路径、未注册工具、未激活 Skill、MCP 单工具禁用与撤权负例证明拒绝；正式图与 worker E2E 验证合法工具、动态激活、重试、摘要和审批仍可用。恢复空值放行行为必须让对应测试失败。摘要另外回读压缩历史文件与 checkpoint，验证主动/自动、溢出与撤权边界；若删除同步入口，搜索和装配证据须证明没有遗留消费者。

### Step 6：【待处理】收敛各自拥有的路径与文件边界

覆盖模式 6、workspace 的路径形态/子目录名校验、重复异常翻译、文件条目组装与排序，以及 Workspace/Provisioner 的五组文件访问契约、工具包的 sandbox scope 解析。runtime 虚拟路径和 UserWorkspace 宿主路径分别在 owning boundary 规整；同一边界的重复规则共用，跨边界通过明确转换连接。产物发布与读取复用已有可见路径规则，补查 `..`、URL、空 Workdir、符号链接和 ELOOP 的实际行为；Workdir 转发层是否保留由现有消费者决定。

验收：真实文件和 Docker 沙盒覆盖合法路径、跳转/链接、错误 scope、空绑定及跨用户访问；回读发布产物与拒绝后的文件状态。不得把不同路径空间合成一个宽松解析器。

### Step 7：【待处理】共用幂等基础语义，保留各域重放策略

覆盖 H9、模式 2 的五份回执惯用法和约 13 处预检样板，以及 promote_input 的锁前检查不对称。复核 inputs/turns/threads、schedules、workspace 的键校验、意图编码、冲突判断与回执装配，共用确实一致的部分；接收响应形状与已删除资源的重放策略仍由各业务域拥有。锁前预检与锁后复查保留明确事务协议，不只把几行代码改成 helper。

验收：真实 HTTP/PG 并发验证同键同意图、异意图、不同用户/APP 作用域、锁等待期间变化和事务回滚；schedules 的软删重放与 workspace 的删除冲突分别保留当前契约。回读 Receipt 与 Input，确认没有重复接受或错误重放。

### Step 8：【待处理】收敛 Run 创建与输入绑定

覆盖 scheduler/runs/turns/cooperation 的四份 Run 创建模式、两份 resume Message 构造，以及 repository 互构与相关锁序。用同一业务用例表达创建 Run、绑定正式 Message/Input、设置 current 的事务步骤；队列消费、人工恢复和协作恢复保留各自入口条件。受影响的 advisory lock 键、常量与 DDL 镜像在其真实 Owner 处明确，不引入可独立维护的全仓键注册表。

验收：真实 PG 与 worker E2E 覆盖普通 FIFO、steer 合批、等待回答/审批、协作恢复和并发重复派发；验证 Input 独立、Message 与 Turn/Run 归属、唯一 current Run、提交后投递及回滚无残留。

### Step 9：【待处理】统一终态收敛与提交后的发布

覆盖 `_finish_run`、`_finish_user_cancel`、committed 路径三份收敛序列、ARQ 投递绕过统一入口，以及 cooperation/核心生命周期双向依赖和 execution 的事件/steer/收尾混合。先明确完成、取消、已提交终态的必要差异，再共用状态结算与提交后发布；按实际职责整理恢复与流消费，不扩大为新的通用状态机。

验收：真实 HTTP、worker、SSE 与 PG 覆盖成功、失败、取消、重复投递、lease 失效、崩溃恢复、steer 与协作等待；回读 Turn.result_run_id、同 Run 结果/错误/用量及终态事件。清理失败与已持久终态的恢复行为分别证明，禁止从相邻 Run 猜结果。

### Step 10：【待处理】厘清 Agent service 与 repository 职责

覆盖 H3/H4、Agent repository 反向依赖用例、路由直调治理策略/内部 commit、Session 授权三份实现、feedback 重复作用域查询，以及 Message/ToolCall 写入、Memory 历史、字节预算与分页装配的混合。先收敛治理和配置用例，再按真实持久化职责整理消息访问；用例拥有事务，查询与受约束写入留在 repository。处理 `commit=True`、mark_thread_viewed/default Agent 的实际提交点、连续空提交和无效用户过滤差异；公开/审计工具结果的序列化与错误文本明确各自契约。

验收：真实 HTTP/PG 证明创建/更新授权、作用域、已删除账号、消息可见性、游标分页、预算边界及事务回滚；worker E2E 证明消息/工具审计和公开结果仍绑定正确 Run。改文件名或搬方法本身不算该步骤完成。

### Step 11：【待处理】身份用例只有一个事务 Owner

覆盖 H5、API Key 的 Web/CLI 双 Owner、repository 自提交、用户 CRUD/资料/头像、部门、UserConfig，以及登录响应与 avatar 归一化、API Key 有效性重复判断。service 统一用例和提交/回滚，HTTP 与 CLI 消费同一领域结果；账号删除涉及 schedules 的策略通过明确域边界编排。OIDC 用例归属、配置单例和同名函数一起复核；进程内 state/login_code 先核实当前多进程部署与有效期契约，再决定是否迁移共享存储，不直接引入新部署能力。

验收：真实 HTTP/PG 验证权限、唯一凭据、幂等派生 secret 重放、撤销 tombstone、账号删除、部门变化与回滚；本地/OIDC 登录回读一致响应与头像。OIDC 若改变存储，补跨进程消费及过期/重复兑换负例；保留当前实现需记明条件和理由。

### Step 12：【待处理】统一知识存储装配与内部数据契约

覆盖 H8、模式 7 的 Milvus schema/索引/embedding 装配副本、两份并发卸载原语、图检索时客户端构造 RPC，以及 chunk/KnowledgeFile 多形状表示。收拢同一存储契约及生命周期；内部语义共用，摄取、持久化、检索与公开响应的必要形状通过明确转换保留。复核过时抽象和 graphs/implementation 依赖方向，保留实际外部连接器消费者。

验收：真实 PG、Milvus 和图谱链路验证摄取、向量/关键词/混合/图检索、索引及来源标题；改变单侧装配的负例能被独立测试拒绝。测量客户端重建与并发预算，不用 mock 次数证明性能；可选服务未运行的范围明确记为未验证。

### Step 13：【待处理】收敛 knowledge 用例与处理行为

覆盖 manager 门面/纯转发、软删事实归属、文件状态词表与历史兼容映射、统计两条交付路径、重名全表扫描/_initialized、大 KB 删除 N+1、evaluation 钩子直改 ORM/全量分页、每 chunk 重建模型，以及 chunking 的隐式参数、静默降级、移植边界和检索默认值分歧。图谱的 `build_graph_payload` 去重分支与 graph_utils 用例归属也在此步骤整理，明确输入、去重语义与实际构建入口。按职责拆为管理/删除/统计与处理/评估/分块两个可独立验收范围；D3 的唯一约束与 D4 的失败统计保持有效。

验收：真实 HTTP/PG/worker 回读软删、历史状态、统计、分页和失败恢复；测量大 KB 查询与锁范围。分块/检索固定输入由独立预期结果验证，非法模型配置与降级可观察；面板默认值与运行时值对照现有/存量 KB，不静默迁移用户配置。图谱构建用重复/冲突实体与关系输入对照独立预期结果，回读实际节点、边与文件关联，证明去重职责调整保持业务结果。

### Step 14：【待处理】整理 Skill 用例与工具注册

覆盖 H7、shared/content 与 skills/tools 双向依赖、ResolvedSkill 来源多份表达、revision/content_hash 多语义、两条安装管线、五份原子发布回滚和重复角色常量；同时处理工具注册表活引用、web_search 直接改私有注册表、catalog 两套读模型及 MCP 的失实注释/重复文案。基于实际消费者拆职责，运行快照契约沿用 Step 5；投影按 uid 全量刷新的必要性与补偿机制先复核，不把当前有意策略当作可随手删除的冗余。

验收：真实 HTTP/PG/文件与工具 E2E 覆盖内置、共享、个人、专属 Skill 的权限、编辑冲突、安装失败回滚、投影撤权和动态 MCP。文件/目录/包修订的比较对象明确，读取工具目录不能修改全局注册结果；保留策略有当前消费者与验证依据。

### Step 15：【待处理】收拢跨域与进程适配依赖

覆盖模式 3 剩余项：健康键、ARQ 连接访问器、JOB_DEFINITIONS 放置、system/dashboard 跨域查询、options 家族两个文件级环与平级域穿透。sandbox/provider 裸 psycopg 读取 agent_envs 的归属与同步约束、两份连接串规整一并复核，共用连接规则，保留当前同步消费者所需的执行边界。再复核 models 的 sync/async HTTP 主体、模型加载双入口、异常类型丢失、三域 PG/Redis 的公共容错部分、documents 硬编码供应商，以及 OIDC/resource_ownership 的跨域编排方向。只移动确属共同技术或叶子契约的内容，各域缓存失效与业务策略继续由原 Owner 维护。

验收：用符号/导入分析确认目标倒置和真实循环消失，完整 API/worker 启动验证 readiness、作业注册、能力发现与投递；真实服务故障/恢复验证异常与缓存行为。沙盒环境读取用真实 PG 对照 AgentEnvRepository 的记录，验证不同连接 URL 形式、缺失/删除配置与同步启动行为一致，避免凭据或配置静默漂移。函数内 import 按解环、可选能力或惰性解析分别说明，不以机械搬动作为验收。

### Step 16：【待处理】命名、文档与剩余局部清理

覆盖模式 5 及第五节尚未关闭的局部项：KnowledgeBase 多义、MilvusGraphService 实际职责、models/catalog/runtime/draft/events/messages 命名、同名 service/repository、state repository 职责、类型注解、包/移植布局、空 debug facade、剩余死导出/参数/透传、丢弃返回值、API limits 的空扩展名列表、category 标签与带内魔法键。命名按当前边界与正式扩展消费者处理；文档随 owning 实现核对，ARCHITECTURE 的 Skill/投影描述先按现源码复核，不能沿用旧行号直接判为错误。

验收：全仓搜索包含正式文档、注册、字符串导入、测试与协议消费者，删除/改名之后旧入口有明确结论；相关 unit、扩展导入/启动、必要的真实接口或页面检查和 docs build 通过。早前明确保留的测试/扩展 API 不能重新按“零生产引用”删除。

### Step 17：【待处理】逐项闭合审计并完成交付

按第一至第五节逐条核对，剩余项必须落到已修复、已清理、有当前依据的保留/不成立，或明确的未完成范围；复合条目按子问题关闭，不以一个相关提交把整行标为已完成。旧分域计数继续标为历史快照，当前完成结论从 owning 源码、决策和证据得出。

每个实施步骤按既有约定单独提交，保留独立回滚范围；非平凡修改先写 proposed decision，证据闭合后转 implemented，并更新本报告对应条目。跨度过大的步骤先分成可独立验收的子步骤，避免把多个事务 Owner 混进一次实现。提交前执行工程契约、相关真实链路、文档链接/build 与独立 Review；未运行和 skip 不记为通过。用户要求合并或发布时再执行相应交付。

---

## 附：分域问题计数（原始审计快照，未扣除已完成项）

| 域 | 高 | 中 | 低 | 备注 |
|---|---|---|---|---|
| agents | 6 | 14 | 15 | 主链路骨架本身无问题 |
| knowledge | 2 | 15 | 16 | manager.py 与 graphs↔impl 是重灾区 |
| extensions/skills | 1 | 10 | 4 | 命名可学习性最差的域 |
| extensions/tools+mcp | 1 | 7 | 4 | 私有属性契约含 fail-open |
| workspace+identity | 2 | 9 | 4 | 事务 Owner 缺失面最大 |
| models/schedules/bg-jobs/documents/system | 0 | 5 | 5 | 唯一可靠性问题在 ModelCache |
| 跨域横切 | 3 | 4 | 2 | 模式 1-3 均为横切 |
