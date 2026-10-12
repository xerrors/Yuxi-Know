# 领域失败与 HTTP 错误表达分离

状态：implemented
类型：architecture
Owner：backend/yuxi/shared/errors.py

## 问题

领域用例直接构造 HTTPException，定时执行、模型工具与文件预览也按 HTTP 类型或状态码识别失败。共享幂等与授权机制需要协议独立的失败契约，现有 API 状态、正文与副作用需要保持兼容。

## 决策

### 实现方案

`backend/yuxi/shared/errors.py` 的领域异常保存业务消息与已有可选业务 code，以异常类型区分非法操作、无权访问、资源不存在、状态冲突、内容过大、输入无效、执行失败、上游失败及超时。类型服务于当前调用方的失败分类；异常本身没有 HTTP 属性。

`backend/yuxi/api/errors.py` 的适配器拥有类型到 HTTP 状态的映射，正式 FastAPI app 注册该 handler，保留既有字符串或 code/message detail。知识库示例问题路由的宽泛捕获透传已知领域失败。HTTP 认证依赖及其他协议错误继续由 API 拥有。

业务模块全部 244 个 HTTPException 抛出点与相应捕获使用领域契约。定时执行按领域拒绝区别可重试故障，文件预览按内容过大类型降级，工具将领域消息转换为 ToolException。事务、幂等意图、授权判定、租约、清理和发布顺序继续由原 service 与 repository 拥有。

## 替代方案

保留领域 HTTPException 会让共享机制继续依赖协议。包含 status_code 的通用异常仅移动依赖，无法建立领域契约。按每条文案建立异常类型会增加没有当前 consumer 的分类表面；当前分类保留实际失败语义与已有业务 code。

## 后果

直接调用领域用例的代码按异常类型及 message/code 读取拒绝结果，HTTP 状态只存在于 API 适配层。输入回执、终态收敛、授权刷新与 Schema 保持当前实现。

非 HTTP 调用方的 str(DomainError) 使用业务文本；新写入的 ScheduledAgentRun、AgentRun 错误、日志及事件文本去掉 str(HTTPException) 的状态码前缀，已有持久记录不重写。Run 的 error_type、终态与输入归属保留原事实。领域拒绝终结定时派发，临时基础设施故障保留恢复意图。

## 验证

使用隔离 Compose 测试环境，复用 API 镜像依赖，运行临时 PostgreSQL 16、Redis 与 MinIO；数据库 Schema、对象和目录由测试创建与清理。共享测试 Schema 播种合成管理员，满足最后管理员的数据库约束。以下 pytest 命令均在该环境通过 docker compose exec api uv run --group test 执行。

| 证据 | 结果与验证范围 |
|---|---|
| pytest test/unit -m "not slow" -q | 2680 passed、60 skipped；服务拒绝类型、预览清理、工具与附件错误保留、OIDC 分类 |
| pytest test/integration/api/test_domain_error_contract.py test/integration/services/test_domain_error_consumers.py -q | 16 passed；正式 app 的真实 TCP 错误协议、异意图 409、PG 原 Input/Receipt、SSE 游标拒绝、定时持久失败与可恢复故障、真实 Redis/ARQ 子进程的 Run/Turn 失败落库 |
| pytest test/integration/services/test_agent_feedback.py test/integration/services/test_agent_input_concurrency.py test/integration/services/test_input_attachments.py test/integration/services/test_live_api_cleanup_run_rows.py test/integration/services/test_oidc_login_transaction.py test/integration/services/test_project_thread_archive.py test/integration/services/test_session_cooperation.py test/integration/services/test_thread_priority_inputs.py test/integration/services/test_scheduled_agent_repository.py -q | 148 passed；真实 PostgreSQL 并发与回滚、MinIO 及文件副作用、接收与树范围、定时唯一性；一项已有 plugin 重写警告 |

AST 比对全部 244 个抛出点的消息、业务 code 与 API 映射，保持原表达式与状态语义。领域边界测试扫描 modules，拒绝 HTTP 导入与 HTTPException 使用；临时恢复 inputs 的原 HTTPException 实现使两项断言失败，临时给状态冲突异常添加 status_code 使三项断言失败，证明守卫能恢复并拒绝目标缺陷。测试完成后恢复正确源码。

工程契约检查、64 项工程检查单测、改动 Python 的 Ruff check、git diff --check，以及文档构建和相关相对链接检查通过。54 个 Python 文件的 Ruff format --check 通过；test_session_config_snapshot.py 存在一处基线参数换行差异，全文件格式检查仍报告该差异，本变更仅迁移其异常断言。

未验证范围：完整 API/worker 启动、真实模型与沙盒成功运行的端到端旅程；ARQ 测试使用真实任务和 worker，仅替换启动时的数据库 Schema 配置以验证领域拒绝的失败落库路径。HTTP 测试使用真实 app 与 TCP，测试身份依赖和启动生命周期由 fixture 管理。首次混合批次缺沙盒清理凭据，附件批次首次缺 MinIO；补正实际隔离资源标记、补充临时 MinIO 后原选择集通过。
