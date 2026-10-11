# 删除没有当前消费者的模块入口

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/agents/runtime/agent_backends/chatbot/graph.py

## 问题

模块结构审计列出了死代码与仅测试引用的入口。清单混合了未装配实现、重复包装、孤立序列化、测试资源创建工具和实际使用的能力，按历史数量直接删除会误伤当前消费者。

## 决策

### 实现方案

删除以当前生产装配、测试、动态调用、导出、配置和正式文档复核为依据的死代码。工具信息旧实现的删除部分取代[模块入口收窄](./2026-10-10-unused-module-entrypoints.md)中保留其实现的决定。完整死亡的命令解析、工具信息实现和 Context 中间件连同孤立测试或导出一起删除；知识库文件树的 manager、基类、只读连接器及专用遍历辅助作为一个删除单元，下载入口使用的原文件路径辅助继续由基类拥有。

Agent 的死查询与孤立 ORM 序列化、知识库和身份域的死 repository 方法、旧分块别名、无人读取的模型状态、MCP 包装和未消费的包级导出按独立职责删除。模型调用、MCP 配置加载、用户管理和知识文件列表继续走既有生产入口；分块来源断言直接调用生产使用的 Markdown 分块入口，预期内容保持原值。死亡实现的孤立测试随实现移除，生产入口的失败、授权和持久化断言保留。旧用户删除测试转到生产 delete_for_admin 入口，继续验证已有 API Key 撤销时间保持不变。

保留有生产消费者的 Agent 序列化、模型包 select_model、知识文件存在性查询、下载路径辅助和 MCP 单服务器工具加载。AuthUtils.generate_api_key 和 decode_token 仍被真实测试资源创建及登录结果校验使用；Run.to_dict、顶层 Run 序号查询、单事件 Redis 写入包装和模型 fallback 参数仍有测试消费者，保留这些消费者所依赖的实现。

清理以一个提交交付，包含删除实现及对应失效的导出、import、孤立测试。传递死亡链保持完整，整体回滚时同步恢复其配套入口。

## 替代方案

保留全部入口会继续维护未装配能力。按审计数量批量删除忽略当前源码与测试的消费者。给死入口添加调用或兼容层会增加维护表面。采用当前消费者复核后的直接删除；未确认的项继续保留。

## 后果

该清理不改变 HTTP 协议、Schema、配置、持久状态、权限执行、运行租约、队列调度或模型可见提示词。正式扩展文档使用的入口继续保留。清理属于无当前行为变化的删除，直接记录 implemented 决定，不新增提案或替代机制。

测试使用已有 API 镜像中的依赖和独立代码挂载，无网络、对外端口及业务数据挂载；旧测试数据库不参与验证。数据库、HTTP 和 worker E2E 未执行，该证据不声称验证持久化或完整用户链路。

## 验证

旧能力不存在：对生产代码、测试、正式文档、脚本和前端搜索删除符号；保留历史审计中的名称以说明审计背景。完整单元测试检验导入、注册与现有业务断言，独立 Reviewer 核对消费者及删除范围。

重新引入条件：出现明确的当前产品、扩展或测试消费者后，在真实 Owner 处实现并验证所需入口；不恢复无消费者的整套旧链路。

实际验证：

- `python3 scripts/verify_engineering_contracts.py`：通过。
- `python3 -m unittest scripts.test_verify_engineering_contracts`：64 项通过。
- `docker compose -f docs/vibe/dead-code-unit.compose.yml exec api uv run --group test pytest test/unit -m 'not slow' -q`：2659 项通过、60 项跳过；该 Compose 文件是本地隔离环境装配，复用已安装依赖，不参与提交。
- 改动 Python 文件的 Ruff、`git diff --check`：通过。
- `pnpm --dir docs run build`：通过，文档相对链接随构建校验。依赖从本机缓存通过 frozen lockfile 安装。
- 独立 Reviewer 审查通过。
