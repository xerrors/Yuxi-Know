# Agents API 机制对齐与客户端直接消费

状态：implemented
类型：architecture
Owner：backend/yuxi/api/routers/public_v1/agents/threads.py

## 问题

外部集成者需要用接近 OpenAI Agents API 的方式创建会话、提交消息、观察工作和读取结果。资源形状、工作状态、配置生效、文件提交与恢复需要共同收敛为容易正确消费的机制。已经生效的统一资源与客户端直接消费由[公开资源决定](2026-10-09-agents-resource-contract.md)拥有，本记录保留整体机制选择，专项实现和证据由对应决定拥有。

读者为 API、运行时和客户端维护者。目标是逐项比较官方与 Yuxi 的实际机制，优先采用更容易正确使用、失败时可恢复且维护成本合理的方案；同等条件下采用官方契约。保留差异需要明确的业务场景和验证，已有实现不构成保留理由。当前资源事实与第一步证据由[公开资源决定](2026-10-09-agents-resource-contract.md)拥有，保留的核心子集边界见[原决定](2026-10-09-agents-session-protocol.md)，历史实施顺序与验收范围见[对齐交付记录](../archived/2026-10-09-agents-api-delivery.md)，当前维护入口见[维护索引](../../agents-api-alignment-plan.md)。

统一资源、会话配置快照与取消专项已生效，分别见[公开资源决定](2026-10-09-agents-resource-contract.md)与[配置及取消决定](2026-10-09-agents-session-lifecycle.md)。draft 附件专项也已生效，见[附件提交决定](2026-10-09-agents-draft-attachments.md)；查询与恢复由[查询恢复决定](2026-10-09-agents-query-recovery.md)拥有。范围包含公开协议、必要的配置和查询机制，以及 Web、CLI、Agent Demo 的同步消费。内部 Thread、Input、Turn、Run 继续承担持久化和执行职责；历史数据迁移、旧接口兼容、部署平台兼容和官方全部托管能力不在范围内。官方 SDK 是否能够结束调用和收集结果须独立验证，不作为设计前提。

## 决策

### 机制对比与选择

官方契约核对日期为 2026-10-09。官方文档用于确认公开行为，不证明其内部数据库、调度器或恢复实现。下表中的选择是针对 Yuxi 场景的设计判断。

| 比较项 | 官方公开机制 | Yuxi 当前机制 | 选择与理由 |
| --- | --- | --- | --- |
| 资源与更新 | [Session 列表](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/methods/list)返回 Session 资源；[更新](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/methods/update)使用 POST 并返回 Session | 统一 Session 资源、POST 更新与稳定创建时间 cursor 已生效 | 保持资源模型统一，减少每个操作独有的解析分支 |
| 消息默认行为 | [空闲时新建 Turn，活动时 steer](https://developers.openai.com/api/docs/guides/agents-api/sessions) | 相同默认方向；另有 FIFO、steer 聚合及协作等待排队 | 保持默认方向；保留显式 follow_up，满足按顺序执行独立工作的需求；等待点限制和协作等待例外明确记录 |
| 工作与结果 | [Turn 查询](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/subresources/turns/methods/retrieve)提供 id、session_id、状态、时间和错误；[Events 与 Items](https://developers.openai.com/api/docs/guides/agents-api/sessions/events)分别承担实时变化和持久内容 | HTTP 与 SSE 的 Turn 核心投影已统一；内部 result_run_id 固定结果归属，输出和等待点在扩展中 | 保持统一投影和有界查询，以目标 Turn 的明确结果恢复 |
| 配置生效时机 | [会话配置](https://developers.openai.com/api/docs/guides/agents-api/configuration)与保存的 Agent 隔离；更新影响后续新 Turn，活动 Turn 保持原配置 | 会话创建保存完整 Context 和有效模型；Input 接收时冻结完整配置；运行身份与授权在执行时解析 | 已对齐会话快照与更新边界；保留 Yuxi 排队 Input 接收时冻结及原子单次覆盖，事实与证据由配置及取消决定拥有 |
| 持久接收 | [事件提交](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/subresources/events/methods/create)以 202 表达接收；SDK 方法不返回业务结果 | 持久 Receipt 与 Input 支持幂等重放、排队和消费归属查询 | 保留有业务价值的回执扩展；与资源分开表达，支持断线后定位同一次提交 |
| 人工等待与控制 | [required_actions](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/methods/retrieve)有明确的函数结果、环境连接和 computer-use 动作类型 | 问答、通用工具审批、协作等待和树控制有独立生命周期 | 保留不等价的 Yuxi 动作；仅在动作、授权与恢复结果等价时采用官方类型 |
| 历史分页 | 官方列表通过 after、limit、order 读取页面 | Session、Turn 和 Items 在授权 repository 中执行有界游标查询 | 保持公开游标语义，查询在 repository 中有界执行；此项是 Yuxi 实现改进，不推断官方存储实现 |

### 实现方案

公开 HTTP 适配层拥有请求和资源模型；agents services 拥有接收、配置冻结、状态与结果，repositories 拥有授权查询与分页。统一投影从这些持久事实生成 Session、Turn 和 Item，HTTP 与 SSE 复用相同核心定义。请求校验与持久响应模型分别维护，以覆盖合法的空工具结果和合并后长文本。

Session 的创建、详情、更新和列表元素使用同一模型；更新入口采用 `POST /sessions/{session_id}`，移除 PATCH 与旧扁平响应。列表采用 after、limit、order；搜索、viewed 和 archive 保留明确的 Yuxi 用途，返回会话资源的操作也使用同一 Session 模型，搜索命中片段放在搜索结果中。归档保留历史，不映射为删除。列表组装批量读取，避免逐项完整快照查询。

Session 核心字段只表达会话事实，扩展显式选取 title、project_id、is_pinned、归档标记、队列及当前工作等有消费者的字段。创建回执放入 `yuxi.receipt`，事件提交返回同一回执模型；回执不覆盖资源状态。公开资源使用 id/session_id，内部 Thread ID 不重复暴露为同义字段。Session 工作状态、归档状态、接收状态和 Turn 终态各有固定含义；最近 Turn 的终态直接作为 Session 工作状态；可继续接收输入由等待点与队列门禁决定。[事实归一决定](2026-10-09-agents-owner-simplification.md)取代本记录的失败转空闲策略。last_active_at 由接收、执行和取消等真实活动更新，标题或 pin 等展示修改保留原活动时间。

HTTP Turn 增加官方核心字段并复用 SSE 投影；业务等待点、取消清理进度、Input/Run 关联和明确结果归入有类型的扩展。Turn 列表及 Session/Turn Items 使用统一分页形状和游标名称。取消仍由执行 Owner 收敛；存在 cancelling 时不能伪报 cancelled，待清理信息通过扩展表达。最终输出必须来自 result_run_id 指向的顶层 Run，不能使用列表末项或最近 Turn 替代本次提交的结果。

创建会话时解析并保存支持范围内的执行配置快照，返回可解释的有效模型；空会话同样需要可解析模型。快照覆盖受支持的 Agent Context 配置，运行时身份和授权结果不进入快照。保存的 Agent 或系统默认值修改不自动改变已有会话。会话更新采用 `agent.model`，省略表示保持原值，null 不作为重置默认模型的方式；尚未实现的官方配置字段明确拒绝。明确的单次 follow_up 模型覆盖采用 `yuxi.model`，公开契约不再使用 model_spec。单次覆盖保留消息与配置原子接收的能力，避免要求客户端先更新会话再发消息而产生竞态；工具审批模式继续作为 Yuxi 配置。更新完成后接收的输入使用新配置，已接收的排队 Input 保留冻结值，活动 Turn 与 steer 沿用活动配置。配置快照不冻结授权，执行时继续核对当前资源可见性和权限。

普通主链路沿用 Session → 事件提交 → Turn/Items；要求精确关联提交或读取 FIFO 队列的场景使用持久回执与 Input 查询。文档示例分别覆盖实时订阅和断线后的回执恢复。SSE 继续作为会话订阅，按目标 Turn 终态回读结果并显式关闭；官方 SDK 的自动收尾能力另设验证，不以示例 helper 替代协议验证。

Web、CLI 和 Agent Demo 直接消费新的 Session、Turn、Items 与回执模型，同步调整调用方法、字段读取、状态处理、流事件及测试。删除取 `session.yuxi` 后复原旧 Thread 响应、重命名回旧字段、双形状解析和旧协议 fallback；三端不能新增兼容旧解析方式的包装层。客户端可以直接读取需要的 yuxi 业务字段，但不能把整个扩展对象当成旧会话响应。界面的排序、文本展示和用户交互可以从新资源计算，计算结果服务实际展示，不构造旧 wire 对象。后端数据库与 LangGraph 使用的 thread_id 保留其内部职责。

Items 分页在完整用户、APP、Session 作用域内执行。游标以稳定公开 item 身份为准，覆盖同一 Message 投影出多个 item 的情况；采用有界查询并为 has_more 多取必要记录，禁止全量读取后截页。分页恢复不能遗漏持久工具结果、混入内部审计或泄露其他会话。

### 图片、附件与 OCR

本节面向附件 API、输入接收用例和三端维护者，目标是让“准备文件”和“正式交给 Agent”具有明确边界。范围包含 draft 上传、消息附件提交、Workdir 文件及私有预处理；通用文件管理平台、完整 Environment API 和自动知识库索引不在范围内。

当前事实由 [附件服务](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/services/attachments.py)、[输入接收服务](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/services/inputs.py)和[执行服务](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/services/execution.py)拥有：上传返回隔离 draft 的 file 资源，产品私有预解析管理派生目录；添加不创建 Session 或 Workdir，发送时持久化 Input 来源，再准备授权 Workdir 文件。模型上下文只列本次和此前已消费的来源。[附件弹窗](https://github.com/xerrors/Yuxi/blob/main/frontend/src/modules/session/ui/AttachmentTmpUploadModal.vue)直接保留上传资源，不调用独立 confirm。接口限制由[公开 API](../../../advanced/agents-public-api.md#图片与文件附件)维护，实现与证据见[附件提交决定](2026-10-09-agents-draft-attachments.md)。

[OpenAI Agents 文件机制](https://developers.openai.com/api/docs/guides/agents-api/environments/files)区分 Files API 文件与运行环境内的文件：创建 Session 时通过 environment.files 提供 file_id 或内联内容及目标 path；环境连接后通过 Environment Files API 添加文件；自托管环境使用自身文件接口或挂载文件系统。借鉴文件引用与运行目录分离的设计，Yuxi 保留真实 Workdir。发送前保持 draft 是本决定的产品选择，官方机制不要求文件必须随消息提交；不为路径兼容新增没有独立职责的 Environment 包装。

附件专项采用以下已生效生命周期：

| 阶段 | 文件与关联语义 | 消费者行为 |
| --- | --- | --- |
| 选择与上传 | 原文件保存在用户与 APP 隔离的 draft 存储，未进入 Project Workdir、Session 历史或模型上下文 | 上传返回稳定文件 id、文件名、类型、大小与过期时间；不要求先创建 Session，不暴露 object_name 或解析目录 |
| 可选预处理 | 产品私有 API 可生成 draft 派生内容，仍未提交给 Agent | 删除或放弃 draft 不修改 Workdir；到期清理覆盖原文件及派生资源 |
| 发送 | 首次创建 Session 的输入与后续消息均携带附件 ID；输入接收用例校验归属与有效期，关联 Input，并将附件写入授权 Workdir | 删除独立 confirm 操作；三端直接使用上传结果提交附件，读取服务端返回的正式引用与路径 |
| 执行与后续使用 | 文件实际归 Workdir 管理；Session/Input 保留提交来源。文件就绪后才允许对应输入执行 | Agent 按需读取文件或调用解析工具；取消已接收的排队输入不自动删除 Workdir 文件 |

附件提交沿用输入的幂等接收语义：响应丢失后重试定位同一 Input 和同一份落盘结果，不能重复生成文件。草稿无效、越权或过期时拒绝提交；写入失败不得启动依赖该附件的 Run。数据库、对象存储与 Workdir 不共享事务，实现必须在接收用例中闭合文件准备、持久关联、失败清理及崩溃恢复；文件就绪且 owning transaction 提交后才能派发。验收覆盖接收前失败可重试、已接收后响应丢失可恢复，不能用前端回滚代替后端事实，也不能把单个数据库事务描述为跨存储原子提交。

发送后落盘遵循共享 Workdir 语义：正在使用相同 Workdir 的 Agent 可以通过文件工具发现新文件；Input 关联用于提交归属，不构成文件隔离。模型附件上下文明确区分本次消费输入的附件与此前已消费的历史附件，不把后续排队输入的附件提前描述成本轮提交。延迟到 Input 消费时才落盘能缩小提前可见窗口，但会增加发送完成与文件可用之间的状态，本决定选择发送时落盘并公开共享语义。

Public 保留 draft 上传与随消息提交文件的能力；独立 OCR 预解析从 Public 路由及契约移出，产品内手动解析由私有 API 承担。私有化遵循产品内部认证边界和文件归属校验，不能只隐藏 OpenAPI。Public 上传和消息参数不再要求调用者选择解析引擎或传递 parsed_object_name；内部预解析产物由服务端随 draft 引用管理。[ocr_parse_file 工具](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/extensions/tools/builtin/ocr_parse_file.py)继续调用公共解析服务，按运行时授权读取文件，将结果写入 Workdir 的 outputs/ocr，并返回路径和短预览。移除直接 Public OCR API 不影响配置了该工具的 Agent 执行解析任务。

图片按用途表达：直接视觉输入使用 input_image 内容块，文件操作使用 draft 附件进入 Workdir；内联图片不隐式获得 Workdir 路径。图片压缩、纠正方向和缩略图等 /images 辅助处理移到产品私有 API，Public 图片输入不依赖此调用。客户端保留完整 MIME 信息并直接构建 API 内容块，不固定重包装为 JPEG，不添加兼容旧 base64 返回结构的包装层。图片文件按需 read_file 或 OCR，不强制对所有图片预解析；只有内联图片且模型不支持视觉时，不能假定 OCR 工具有可读取的文件路径。图片 URL 的支持范围以实际校验和能力为准，不因使用标准内容块就宣称支持尚未实现的远程 URL。

## 替代方案

| 方案 | 取舍 |
| --- | --- |
| 保持核心子集与客户端旧形状转换 | 改动较少，但继续维护多套公开响应、状态解释和客户端解析，不满足直接消费 API 的要求 |
| 全面复制官方接口与运行机制 | 托管环境、外部工具和授权动作缺少等价实现；会扩大范围，并可能削弱现有队列、持久回执和结果归属保证 |
| 重新设计一套更少概念的专有接口 | 减少表面字段，但偏离用户希望复用官方设计的目标，也可能隐藏并发提交与结果关联的必要信息 |
| 官方机制优先，保留有场景证明的扩展 | 采用本方案；资源与默认行为尽量一致，FIFO、回执、等待点与权限机制按真实差异保留并测试 |

## 验证

本节保留接口对齐阶段的原始验收范围；附件存储与准备编排、唯一配置快照和 Session 状态策略由[事实归一决定](2026-10-09-agents-owner-simplification.md)部分替换，当前实现与对应证据以该记录及源码 Owner 为准。

资源、配置、调度与取消的证据分别由对应决定拥有，附件由附件提交决定拥有，分页与客户端恢复由查询恢复决定拥有。外部视觉/非视觉模型探针因未配置模型而 2 skipped；官方 SDK 完整调用另列 P1，未执行范围不计为协议验收通过。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 创建、详情、更新和列表返回相同 Session 核心模型，回执不改变字段含义 | 文档统一但真实 HTTP 仍返回两种对象 | public_v1/agents 的 schemas、responses、threads | `docker compose exec -T api uv run --group test pytest test/unit/routers/test_public_session_contract.py test/integration/api/test_public_agents_key_boundary.py -q`；补齐实际更新和列表回读 | 恢复扁平列表、receipt.status 覆盖或旧 PATCH 后，独立契约断言失败 | Passed |
| HTTP 与 SSE 对同一 Turn 使用相同核心身份和终态，结果绑定明确 Run | 查询和事件各自正确但互相矛盾，或取到相邻轮次结果 | services/events、turns、public_items | `docker compose exec -T api uv run --group test pytest test/e2e/test_openai_events_e2e.py test/e2e/test_agent_lifecycle_e2e.py -m e2e -q`；回读 Turn、结果和数据库归属 | 提前发布取消终态、交换相邻 Run 结果或保留 HTTP running 旧枚举时失败 | Passed |
| 空闲输入开启新轮，运行中默认 steer，显式 follow_up 保持 FIFO | 为接口简化改变运行时调度或丢失输入 | services/inputs、scheduler | 配置及取消决定的 PostgreSQL priority、cooperation 与 worker 生命周期命令；回读 Input、Turn 与 Run | 把运行中默认改为排队、重复消费或绕过等待点时失败 | Passed |
| 配置快照和更新只作用于正确输入，权限仍实时生效 | 保存的 Agent 修改影响旧会话，或更新追溯修改已接收输入 | services/inputs、input_config、threads、preparation、runner | 配置及取消决定的双模型/单次覆盖、默认冻结 PostgreSQL 与权限撤销 worker E2E 命令；比较持久配置、manifest 与实际请求 | 修改 Agent/系统默认、更新前后排队、活动 steer、单次覆盖与撤权分别核对结果 | Passed |
| 等待取消保留已完成工具结果和业务增量，提交后失联仍能恢复 | 丢失 sibling pending writes、历史重复 call ID 误判，或提前伪报终态 | services/turns 与原图 checkpoint reducer | 配置及取消决定的真实 StateGraph 崩溃测试、并行问答/协作等待取消 worker E2E；回读前后 checkpoint | 恢复先写取消消息、历史全局 call ID 判定或 END 后不补结果时失败 | Passed |
| 幂等回执始终定位同一次提交，排队时不虚构 Turn | 使用最近 Turn 或重试重复建 Input | services/inputs 与 Input/Receipt repositories | 生命周期与 Key scope E2E；断开接收响应后复用同一幂等键并回读数据库 | 并发新输入后错绑旧回执，或控制事件伪造 input_id 时失败 | Passed |
| Session、Turn 和 Items 游标分页有界且保持作用域 | 只检查返回数量，实际全量读取或跨 APP 定位游标 | agents repositories 与 services/public_items | `docker compose exec -T api uv run --group test pytest test/integration/api/test_public_session_items.py test/integration/api/test_public_agents_key_boundary.py -q`；真实 PostgreSQL 查询范围、稳定排序、多 item 同源及并发追加断言 | 恢复全量读取、漏掉同 Message 的后续 item 或使用跨会话游标时失败 | Passed |
| 三端直接消费新资源，不复原旧协议 | HTTP 边界解包 yuxi，测试仍靠旧 fixture 通过 | frontend/src/apis 与 session 模块；packages/yuxi-cli、agent-demo | Web lint/unit/build 与真实浏览器；CLI typecheck/test；Demo unit/browser 和真实 HTTP 冒烟；补旧解析路径搜索与完整消费者 diff Review | 使用只含新契约的真实响应，旧 thread_id/status 读取或双形状 fallback 不能通过验收 | Passed |
| 长期 SSE 以目标 Turn 持久终态和结果判定成功 | 断流或其他 Turn 完成被当作成功 | services/events、turns 与三端观察 | worker/SSE E2E；三端故障注入与结果回读，见查询恢复决定 | 无增量结果、Redis 过期、相邻 Turn 与协作等待 | Passed |
| 指定版本官方 SDK 的完整调用 | SDK 自动收尾或收集结果与实际订阅不符 | 官方 SDK 与外部消费方 | P1 独立执行带超时的冒烟 | SDK 返回不能替代持久业务结果 | Not run |
| draft 在发送前不进入 Workdir、Session 历史和模型上下文，首条输入无需提前 confirm | 界面显示草稿但文件已对 Agent 可见，或上传强制创建空 Session | services/attachments、inputs、execution；前端附件弹窗与发送流程 | 扩展真实 HTTP 附件测试与浏览器验证；在上传、可选私有解析、移除、发送各阶段回读存储、Session/Input 与实际模型请求；验证过期清理 | 恢复 confirm 提前落盘、跨用户或 APP 引用、过期引用、将未发送或后续排队附件注入当前输入时失败 | Passed |
| 附件提交可幂等恢复，文件就绪且事务提交后才派发，取消排队不隐式删文件 | 重复落盘、缺文件执行、崩溃后静默丢失或错误清理共享文件 | services/inputs、attachments、scheduler；workspace 文件边界与 Input/Receipt repositories | 真实 PostgreSQL、对象存储、Workdir 与 worker E2E；注入文件写入失败、进程中断与接收响应丢失，重试后回读 Input、文件数量与字节内容；验证共享 Workdir 的发送后可见性 | 提前派发、同幂等键重复落盘、清理已接收文件或取消排队自动删除文件时失败 | Passed |
| OCR 预解析与图片辅助处理退出 Public；Agent 解析工具及标准图片输入仍可使用 | 只隐藏文档、私有入口越权、图片 MIME 被改写或移除 API 连带禁用工具 | Public capabilities 与私有路由认证；services/attachments；extensions OCR 工具；三端图片消费 | 真实 HTTP 验证 Public 旧入口移除和私有认证/归属；运行 OCR、read_file 多模态 E2E，回读 Markdown 与资源；三端以 PNG/JPEG 内容块验证实际请求 | Public OCR 仍可调用、跨作用域私有解析、PNG 被包装为 JPEG、无文件路径却宣称 OCR 成功时失败 | Passed |

文档引用和构建由 `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`、`cd docs && pnpm run build` 与 `git diff --check` 验证；这些检查不替代上述产品行为证据。

## 后果

三端直接消费新契约会扩大字段、状态和 fixture 的同步改动范围，需要在同一交付中完成生产调用方。测试数据按公开 wire 契约编写，不能由生产转换器生成期望对象，也不能通过增加旧解析包装让测试继续通过。

会话配置快照改变默认模型和 Agent 修改的影响范围：空会话创建也会验证有效模型，已有会话的配置通过显式更新修改。队列接收与更新的顺序需由 owning transaction 确定；快照不能保存已撤销授权的使用资格。

统一状态枚举、Session 活动时间及多 item 分页需要验证持久来源，不能通过填充常量、字符串替换或先取全量再截页满足响应 schema。权限可见性与游标查询必须在同一作用域内执行。

并行问答与协作等待的取消采用原图状态提交，结果保留与崩溃重试由[配置及取消决定](2026-10-09-agents-session-lifecycle.md)拥有。清理失败仍保留 cancelling，恢复扫描处理；协议投影持续表达实际清理进度。

官方文档和 SDK 可能演进。实施时复核所用版本，只对经过协议与实际消费测试的范围声明兼容；没有对应消费者的托管能力保持未实现。
