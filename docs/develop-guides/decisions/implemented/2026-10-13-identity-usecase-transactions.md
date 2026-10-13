# 身份用例与事务归属收敛

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/identity/services/users.py

## 问题

API Key 的 Web 创建与 CLI 兑换重复派生和持久化流程，部分仓储隐式提交；用户管理、资料、头像、部门和偏好写入在 HTTP 路由编排。调用方难以判断失败时哪些事实已经提交。登录响应重复组装使 OIDC 与密码登录头像不同。账号删除仓储直接操作 schedules，资源转移把跨域治理耦合到 identity。

## 决策

### 实现方案

用户管理、部门变更、偏好保存和 Web 凭据管理的 service 拥有提交与失败回滚；仓储只执行查询和 flush。凭据签发复用 `services/api_keys.py` 的不提交操作，Web 创建在写入末尾提交，CLI 兑换把会话消费与凭据保存一起提交并在失败时回滚。派生上下文、request_id、意图哈希、撤销 tombstone、重放窗口和公开错误状态保持原契约。API Key 鉴权与 CLI 重放共用模型有效性判断。

用户管理保留共同身份锁和部门范围检查，角色提升消费同一事务已经锁定的用户。用户仓储软删除并撤销凭据，service 在同一事务调用 schedules 仓储清理任务，删除策略由 owning 域实现。部门写入必须注入调用方事务。偏好保存使用 UID 唯一约束上的 upsert，移除内部 commit、rollback 与重试。头像 service 消费中立字节，上传成功后提交引用；对象存储与数据库没有分布式事务，数据库提交失败可能留下未引用的对象，沿用当前上传边界。

系统模块拥有共享资源所有权治理，保留 Agent/Skill 的发布入口和既有锁序。身份域不再反向编排这三个资源域。三个登录入口共用 `services/login.py` 的结果投影与 User 公开头像规范。OIDC 配置通过显式读取入口获取，API 启动仍以 required component 校验配置；Redis state/result、浏览器绑定、PostgreSQL 会话以及五分钟/一分钟有效期保持现有协议。密码登录、CLI 授权创建/批准仍由原服务提交，异常时的会话清理由请求数据库上下文负责。

identity 的 services/repositories 保留现有 namespace package，不新增空 `__init__.py` 或兼容导出。没有新的公开接口、Schema、认证方式或通用事务框架。

## 替代方案

- 保留现状：事务与响应重复继续增加修改成本。
- 用通用装饰器隐藏提交：主流程看不到提交点，CLI 复合写入更难组合。
- Web 与 CLI 使用各自签发函数：重复安全关键的派生输入与持久化装配。
- 更换 OIDC 存储：当前 Redis/PG 已满足部署与有效期契约，没有新增消费者。

## 后果

修改身份写用例时，从 service 可以直接找到提交点；仓储能参与更大事务而不提前提交。部署参数仍来自环境，不提供动态配置 API。OIDC 短期结果仍可在有效期内幂等恢复，账号与会话撤销每次回读。锁键取值保持持久兼容，应用和 DDL 从身份模型中的同一具名常量构造。

## 验证

真实 HTTP/PostgreSQL 测试回读凭据唯一性、并发重放、撤销 tombstone、CLI 消费、跨部门权限、部门迁移、账号删除、配置并发写入和失败回滚；OIDC 使用真实 Redis 与 TCP 签名 provider fixture，覆盖密码/OIDC/个人资料头像一致性。头像上传还回读真实 MinIO 字节并删除测试对象。

负向控制在独立测试进程恢复 API Key repository 的内部 commit，回滚用例在新连接读取到被提前提交的名称而失败。CLI 提交失败的负例先证实待写 Key 会被后续提交，再验证用例主动回滚。部门无事务写入和无效 OIDC 启动配置均有直接拒绝测试。

实际验证命令：

```bash
docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q
docker compose exec -T api uv run --group test pytest test/integration/services/test_identity_usecase_transactions.py test/integration/services/test_identity_admin_service.py test/integration/services/test_api_key_user_lifecycle.py test/integration/services/test_oidc_login_transaction.py test/integration/identity/test_identity_permission_constraints.py test/integration/services/test_scheduled_agent_repository.py::test_account_soft_deletion_removes_scheduled_job_history -q
python3 scripts/verify_engineering_contracts.py
python3 -m unittest scripts.test_verify_engineering_contracts
```

完整 unit 2741 passed、60 skipped（测试容器未挂载仓库根部，源码布局/工程契约用例按既有条件跳过）；集成 61 passed；工程检查单测 64 passed。首轮 unit 的头像 mock 仍指向旧路由导入，迁移后通过；集成首轮的 OIDC 密码登录受跨测试事件循环 Redis 连接影响，fixture 改为消费当前循环真实 Redis 后通过。前述失败不计通过。

工程信任检查、变更的 38 个 Python 文件 Ruff/format、5 份 Markdown 的 23 个相对链接和 `git diff --check` 均通过；`node docs/node_modules/vitepress/bin/vitepress.js build docs` 构建通过。主工作区 `/api/system/ready` 返回 200，仅证明装配就绪；业务证据来自上述回读。

第三方生产 IdP、浏览器 UI、生产部署和外部模型未执行，本次使用真实 TCP 签名 provider fixture；skip 不计通过。

旧能力不存在：路由编排目标身份写事务、API Key repository 提交、UserConfig.save 隐式提交和 import 时固化 OIDC 配置均移除；身份仓储不再导入 schedules ORM，identity 不再拥有 resource_ownership。

重新引入条件：只有新的独立消费者或部署契约证明需要新的事务入口、响应差异或 OIDC 存储，才重新提出决策。
