# Public API 凭据与终端用户身份归属

状态：implemented
类型：architecture
Owner：backend/yuxi/modules/identity/services/public_auth.py

实现位置更新：模型注册现由 `backend/yuxi/infrastructure/postgres/models.py` 拥有，见 [2026-10-21 后端边界收敛](./2026-10-21-backend-boundary-and-provider-catalog.md)。本记录保留当次命令与证据。

## 问题

API Key 校验原位于 HTTP dependency，App 终端用户解析原位于 Agent 目录服务。身份规则分散，其他业务入口需要依赖 agents 才能复用终端用户身份。

## 决策

### 实现方案

identity 的 `public_auth.py` 校验 Key 的有效性与所属用户，并按 JWT、无 App full Key、App Key 解析资源用户。`APIKeyRepository` 拥有摘要查询，`UserRepository` 拥有用户查询与终端用户并发创建。身份服务使用领域错误，API dependency 读取 Header、映射 HTTP 错误并执行 API 面路径限制。Public Agent context 保留 ActorScope 转换，Agent 资源可见性继续由 agents 拥有。

保持当前身份行为、错误响应、默认终端用户规则和事务提交点：Key 最近使用时间在 API 面授权后提交；App 身份在 identity service 解析后提交。不增加 App 实体、配置、依赖或通用认证框架。App Key 的调用方声明 end_user_id，该标识没有独立终端用户凭据验证。

## 替代方案

保留分散实现会继续让身份服务依赖 Agent 目录。只迁移终端用户 helper 无法收敛 API Key 身份校验。引入统一认证框架超出当前消费者需求。

## 后果

身份规则拥有一个业务 Owner，HTTP 适配与业务资源授权保持各自职责。service 需要传入已认证的 owner 与 Key，由 API dependency 保证来源。持久身份唯一约束、权限范围和公开协议保持一致。

## 验证

验证在独立 phase1 Compose 槽位执行，使用既有测试环境凭据初始化测试管理员。工作树中其他既有改动保留。

| 验收主张 | 语义 Owner | 证据与负向案例 | 结果 |
|---|---|---|---|
| Key 校验与 App/end_user 解析归属 identity | identity services/repositories | 检查真实调用链；旧 `_verify_api_key` 与 agents 身份解析入口已删除；全新 Reviewer 独立审查完整本次 diff | Inspected，无阻断问题 |
| 凭据与身份隔离行为保持一致 | identity 与 API dependencies | 有效、未知、停用、撤销、过期 Key；非法外部标识；JWT/full Key 不得伪造 end_user；真实 PostgreSQL 回读并发同身份、跨 App 身份与停用用户 | 相关 unit 19 Passed；集成 26 Passed、1 failed，见下述范围 |

实际命令：

```bash
docker compose exec api uv run --group test pytest test/unit/routers/test_api_key_security.py test/unit/services/test_public_agents_api.py -q
```

该命令在依赖同步阶段因容器内 `yuxi.egg-info` 无写权限失败，未进入 pytest。后续使用现有虚拟环境：

```bash
docker compose exec api uv run --no-sync pytest test/unit/routers/test_api_key_security.py test/unit/services/test_public_agents_api.py -q -p no:cacheprovider
docker compose exec api uv run --no-sync pytest test/unit -m 'not slow' -q --tb=short -p no:cacheprovider
```

相关 unit 为 19 passed。全量为 2241 passed、55 skipped、3 failed：两个 DOCX parser 测试因第三方 docling 的 `UnicodeToLatexEncoder` 未定义失败，另一个 skills middleware 测试未获得期望的知识库工具。本次未修改这些模块；三个失败单独重跑仍复现，不能宣称全量通过。

```bash
docker compose exec api uv run --no-sync pytest test/integration/api/test_public_end_user.py test/integration/api/test_public_agents_key_boundary.py test/integration/api/test_public_knowledge_key_boundary.py test/integration/api/test_apikey_router.py -q --tb=short -p no:cacheprovider
```

直接运行结果为 24 passed、3 failed。两个测试进程 ORM 未注册 `AgentEnv`，通过 shipping 的模型注册入口预加载后重跑：

```bash
docker compose exec api uv run --no-sync python -c 'from yuxi.bootstrap.models import load_models; load_models(); import pytest; raise SystemExit(pytest.main(["test/integration/api/test_public_end_user.py", "test/integration/api/test_public_agents_key_boundary.py", "test/integration/api/test_public_knowledge_key_boundary.py", "test/integration/api/test_apikey_router.py", "-q", "--tb=short", "-p", "no:cacheprovider"]))'
```

结果为 26 passed、1 failed。剩余 `test_legacy_external_list_matches_public_v1` 仍期望旧知识库入口返回 200，实际为 404；相关路由未在本次变更中修改。Key 与 App/end_user 的身份、撤销、API 面限制和持久化测试通过。未执行真实模型或 worker E2E，本次未改变执行链路。

```bash
python3 scripts/verify_engineering_contracts.py
python3 -m unittest scripts.test_verify_engineering_contracts
pnpm --dir docs run build
git diff --check
uvx ruff check backend/yuxi/api/dependencies/auth.py backend/yuxi/api/routers/public_v1/agents/auth.py backend/yuxi/modules/agents/services/directory.py backend/yuxi/modules/identity/repositories/api_keys.py backend/yuxi/modules/identity/services/public_auth.py backend/test/unit/routers/test_api_key_security.py backend/test/unit/services/test_public_agents_api.py
uvx ruff format --check backend/yuxi/api/dependencies/auth.py backend/yuxi/api/routers/public_v1/agents/auth.py backend/yuxi/modules/agents/services/directory.py backend/yuxi/modules/identity/repositories/api_keys.py backend/yuxi/modules/identity/services/public_auth.py backend/test/unit/routers/test_api_key_security.py backend/test/unit/services/test_public_agents_api.py
```

工程契约、64 项契约 unit、文档链接与构建、补丁空白检查和本次 7 个 Python 文件的 Ruff 检查均通过。容器内未安装 Ruff，使用宿主的 `uvx ruff` 验证。独立 Review 未重复运行测试，其测试证据依据上述实际执行结果。
