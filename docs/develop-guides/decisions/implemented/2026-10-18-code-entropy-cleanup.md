# 收敛闲置工具入口与知识文件提交逻辑

状态：implemented
类型：simplification
Owner：frontend/src/modules/knowledge/model/knowledgeBase.js

## 问题

存储便捷方法、旧图片投影、前端 API 包装与网络搜索 SDK 存在已退出生产调用链的维护表面。知识文件的选中解析、全部待解析、选中入库、全部待入库又分别维护相同的 loading、作业登记、刷新和错误反馈。

本记录面向维护者，解释本轮内部清理的范围、取舍和证据。体检参考 [jscpd](https://github.com/kucherenko/jscpd/blob/master/skills/jscpd/SKILL.md) 与 [reclaim-code-entropy](https://github.com/Yevanchen/reclaim-code-entropy/blob/main/skills/reclaim-code-entropy/SKILL.md)，将扫描输出作为候选，结合动态入口、历史用途、文档承诺和当前消费者判定是否删除。

## 决策

### 实现方案

`MinIOClient` 删除无生产、测试、配置或文档调用方的 `upload_file_from_path`、`adelete_bucket`、`temp_file_from_url`。文件读取、对象字节预算、响应释放和目录生命周期继续由现有调用链拥有。`PostgresManager` 删除闲置的 `is_postgresql`、`get_async_session`、`async_check_first_run` 和不提交调用方事务的空 `commit` 包装，保留真实 session 上下文、迁移锁、初始化检查与连接关闭。

前端 `ErrorHandler` 删除未使用的网络错误映射、异步包装和处理器工厂及对应导出。聊天、验证错误和底层 HTTP 错误语义保持现状。知识库 store 保留四个显式动作和各自 API 参数，在模块内部共用提交后的状态处理；登记回调仍在请求前捕获账号与知识库，错误与成功文案、空选择返回值和刷新时序保持不变。

网络工具由 `modules/extensions/web/services.py` 使用 HTTPX 调用固定供应商端点；生产代码、测试、脚本与扩展文档均不消费 `langchain-tavily` 或 `tavily-python`。删除这两项直接依赖及对应锁文件节点，保留其他包的锁定版本。隔离测试容器卸载两个 SDK 后验证工具装配与单元测试，防止旧镜像中残留依赖掩盖导入问题。

前端 API 层删除知识库中未被消费的添加已上传文档、旧查询、ZIP 上传/处理和统计包装，以及 Dashboard 的三项单独统计包装；实际上传、查询、批量统计与回退继续使用已有调用链，HTTP 路由保持原样。后台作业 repository 删除未被登记服务使用的 `create_in_session`；真实提交仍走 `create_or_get_in_session`。Agent 输入模块删除仅剩孤立测试消费的 `extract_image_contents`，同步删除该旧投影的专用测试；当前历史协议继续由 `serialize_public_items` 及其多图、纯文本与原始内容隔离测试证明，输入恢复测试保留。

此次范围是内部维护表面，公开协议、持久化格式、权限规则、动态插件发现、会话生命周期和界面样式保持现状。

## 替代方案

- 保留所有代码：无行为风险，但继续维护无消费者入口与四份相同流程。
- 只删除闲置入口：可降低静态维护成本，仍留下知识库作业处理重复。
- 引入通用异步操作框架：增加跨模块抽象与配置面，当前没有消费者需要。
- 按扫描结果批量删除：动态加载的预设和工具不能由静态导入数量判断可达性。

## 后果

生产源码净减少 381 行，清除 20 个闲置方法或 API 入口；依赖声明与锁文件另减少 35 行。保留的第三方依赖锁定记录逐项一致。知识文件提交只维护一段共同处理逻辑，四个业务动作仍显式选择各自端点与参数。

`knowledge_base_qa.py` 通过递归发现进入预设集合；`SandboxCommand` 由 ORM 注册与表名 SQL 消费，均保留。单事件 Redis 写入和顶层 Run 序号查询仍被真实存储测试消费，保留其独立 oracle。安全校验、对象读取预算、响应释放、session 事务与动态装配没有变动。

静态扫描不能证明动态入口不可达，也不能把相似样式或不同业务 Owner 的重复片段自动判定为缺陷。本轮不添加长期扫描配置或重复率 gate；扫描值仅是这次审计的派生证据。

## 验证

旧能力不存在：生产、测试、脚本、配置与当前文档中，删除的唯一符号只剩本决策说明；后台作业的创建调用均进入 `create_or_get_in_session`。锁文件不再含两个 Tavily SDK，隔离容器卸载后用 `importlib.util.find_spec` 确认两个模块均不存在。历史记录中的名称保留作为背景。

重新引入条件：出现有明确 Owner 的产品或扩展消费者，需要具体能力并提供相应行为测试；不恢复整套无消费者的便捷接口。

独立 Compose project `yuxi-entropy-df40` 复用 API 镜像，使用当前仓库只读挂载、独立临时目录和 `network_mode: none`，不挂载业务数据。以下后端命令在该 project 的 api 服务执行，`UV_NO_SYNC=1` 使用镜像已安装依赖；两个已删除 SDK 已从测试容器卸载。

| 证据 | 命令与结果 |
|---|---|
| 存储保留契约 | `uv run --group test pytest test/unit/storage -m 'not slow' -q`：清理前后均 81 passed |
| 当前历史、输入恢复与作业登记 | `uv run --group test pytest test/unit/services/test_background_jobs.py test/unit/services/test_agent_input_messages.py test/unit/services/test_session_history_images.py -q`：55 passed |
| 无 SDK 的搜索与工具装配 | `uv run --group test pytest test/unit/agents/test_web_search_provider.py test/unit/services/test_tool_registry_contract.py test/unit/agents/test_builtin_discovery.py -q`：53 passed |
| 后端全量 | `uv run --group test pytest test/unit -m 'not slow' -q -rs`：2923 passed、4 skipped；这 4 项需要容器没有安装的 Docker CLI |
| 补跑 Compose dotenv | 宿主 `uvx --from pytest --with pytest-asyncio --with pyyaml pytest --noconftest backend/test/unit/config/test_init_noninteractive.py -k environment_values_roundtrip -q`：4 passed；独立配置测试直接执行真实 Compose 解析，不加载后端服务 fixture |
| 知识库提交行为 | `pnpm --dir frontend exec node --test test/unit/knowledge_base_store.test.js`：17 passed；新增参数、反馈、空选择和 loading 用例在重构前也通过 |
| 前端 API 保留契约 | `pnpm --dir frontend exec node --test --test-concurrency=1 test/unit/api_boundary.test.js test/unit/file_upload_folder.test.js test/unit/dashboard_thread_stats.test.js`：26 passed |
| 前端全量与构建 | `pnpm --dir frontend run lint:check`、`pnpm --dir frontend run test:unit`、`pnpm --dir frontend run build`：Passed，unit 709 passed |
| 锁文件与 Python 格式 | `uv lock --project backend --offline --check`、Ruff 0.16.4 对改动 Python 文件的 `check` 和 `format --check`：Passed |
| 工程与文档 | `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`、`pnpm --dir docs run build`、`git diff --check`：Passed，verifier unit 66 passed |

jscpd 5.4.1 精确扫描使用 `--min-tokens 80 --min-lines 8`，扫描 `backend/yuxi`、`frontend/src` 和 `packages/yuxi-cli/src`、`packages/agent-demo/src`，排除依赖、构建产物、测试及锁文件；同配置结果由 43 组、0.4% 变为 41 组、0.3%。独立 `--ignore-identifiers --min-tokens 120 --min-lines 10` 扫描得到 52 组候选，包含精确片段与重命名相似片段，不作为精确重复的前后指标。

三名独立子智能体分别复核后端删除候选、前端消费者和累计完整 diff；保留项按实际消费者与风险裁定。真实 HTTP、PostgreSQL、worker、浏览器与外部供应商探针为 Not run；本轮证据证明内部等价清理及装配，不声称验证完整部署链路。
