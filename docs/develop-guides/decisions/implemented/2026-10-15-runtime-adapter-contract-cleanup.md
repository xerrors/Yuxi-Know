# 运行适配器与依赖契约清理

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/models/embed.py

## 问题

Embedding 适配器继续接受 name/url/model_id 等旧别名，并在 provider 已完成凭据解析后再次把值当环境变量名。无生产或测试消费者的查询别名、模型信息字典函数、Agent 批量查询与 Workdir 前缀读取增加维护面。BaseAgent 的 checkpointer 异步方法只转发同步 factory。aiosqlite 只有测试消费者却属于生产依赖。

## 决策

### 实现方案

Embedding 构造只接收当前 selector 产生的字段，provider 凭据解析结果直接交给 executor；删除无消费者方法。图编译、性能探针与开发示例直接使用 PostgreSQL checkpointer factory，每次构图独立实例的语义由 factory 和真实数据库测试证明。aiosqlite 移入 test 依赖组，更新锁文件。性能探针直接装配正式 WorkerSettings，包装 coroutine 时保留 ARQ Function 的任务选项。

## 替代方案

- keep：继续维护旧别名和重复凭据解析，拒绝。
- narrow：只改文档，实际调用面仍不收窄，拒绝。
- replace：为旧形式新增适配器，无消费者，拒绝。
- remove：收窄为真实 producer/consumer 契约，采用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| Embedding 使用 provider 确定的配置与凭据 | 二次环境解析覆盖正确值 | embedding selector / executor | 相关 unit | 与环境变量同名的实际凭据不得被替换 | Passed：HTTP mock 回读实际 Authorization；恢复二次解析后精确失败 |
| 图保持独立 saver 与共享 PG pool | 删除 wrapper 误引入缓存 | checkpointer / graph | unit、真实 PG checkpoint 并发恢复 | 持 A 锁时 B 能读取且字节不串线程 | Passed：真实 PG 并发 checkpoint 1 passed；graph 与 probe unit |
| 无消费者入口与生产 SQLite 依赖删除 | import/export、fixture 或交付仍依赖 | 对应源码 / pyproject / lock | 调用搜索、unit、uv lock check | 旧能力不存在 | Passed：调用搜索、backend unit 2654 passed；uv lock --project backend --offline（195 packages） |

旧能力不存在：Embedding 旧构造参数、encode_queries/aencode_queries/get_embedding_model_info_by_id、AgentRepository.list_by_slugs、Workdir.read_file_prefix、BaseAgent._get_checkpointer 及生产 aiosqlite 声明不存在。

重新引入条件：出现明确当前 consumer 及单独边界责任；不为未来假设恢复别名。

## 后果

不改变模型公开配置协议、知识索引或文件读取预算。开发/CI 镜像仍按当前装配安装 test 组；依赖分组准确表达 SQLite 只用于测试。

性能入口验证：`test/unit/performance/test_probe_bootstrap.py` 在独立进程中按两种 `MATRIX_FINE_TIMING` 模式安装实际探针，检查真实 WorkerSettings 的所有 Function 注册选项及其他后台作业注册；修改前因旧事件导出名失败，修改后 2 passed。开发示例和性能入口同步直接调用 PostgreSQL factory。

当前配置消费者：provider 的 `api_key_env` 是用户可指定的环境变量名，凭据解析由 provider 拥有；不能依据变量名没有固定字符串读取就删除模板。当前开发/CI 镜像明确安装 test 组，因此 aiosqlite 的测试装配仍保留。

真实 worker 装配验证：隔离 API 与 `test.performance.probe` 包装的正式 ARQ WorkerSettings 运行核心生命周期、扩展路径和协作树 29 项 E2E，全部通过；共享 PostgreSQL checkpoint、后台作业注册与 Cube 文件挂载均使用当前实现。
