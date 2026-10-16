# 沙盒文件展示与用户挂载保持一致

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/workspace/runtime_files.py

## 问题

同一个 `/home/user/skills/<slug>/...` 路径，VM 和 Agent 文件工具读取用户投影，HTTP 预览、下载与保存却读取 Skill 来源。来源与投影不同步时，展示的文件不是 Agent 实际读取的文件。部署示例使用 Cube 默认白名单之外的节点路径，chat-widgets 则把 API 存储名称混入模型使用说明。

## 决策

### 实现方案

`RuntimeFiles` 统一持久 runtime 路径的读取和有界文件导出：Workspace 复用 owning filesystem，Skills 从当前用户投影逐层 no-follow 读取。Agent artifact service 在原有 Thread、APP、用户及当前 Skill 授权检查后调用该边界；Skill 行锁覆盖文件导出，缺失投影明确失败，不回读平台来源，也不唤醒 VM。删除 artifact service 的独立来源文件复制路径。

[部署示例](../../../advanced/sandbox-operations.md#原生执行节点)使用 `/data/shared/yuxi` 下的两项现有节点根。VM 只挂载用户 Workspace 与只读授权投影；存储结构、环境变量、公开协议和用户 VM 生命周期保持现有契约。chat-widgets 只说明实际沙盒路径、当前工作目录与展示动作。

本决定更新[图片展示决定](./2026-10-12-widget-sandbox-images.md)中的文件读取约定；Image/ImageGroup 协议与交付物登记职责仍由原决定拥有。

## 替代方案

- 保持来源读取：不能保证相同 runtime 路径对应相同字节。
- 读取前自动刷新投影：预览引入整套 Skills 同步、锁与写入副作用，不是展示的职责。
- 全部通过 VM 读取：让持久文件展示依赖 VM 唤醒与远端命令，且失去当前宿主 no-follow 边界。

## 后果

已授权但尚未生成投影的文件返回不存在；执行准备和 Skills 用例继续拥有投影刷新。持久文件预览范围保持不变，VM Home 与临时文件先显式保存到工作目录。并发发布可以让一次读取获得已打开的旧投影或明确失败，不承诺预览与先前工具读取的跨请求快照。

节点根、API 容器根与模型路径是各自命名空间的坐标，配置要求它们指向相同底层文件，不增加兼容路径或自动探测。默认部署不依赖额外挂载白名单；已有用户 VM 无需重建。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 工具、预览、下载与保存读取用户投影字节 | 来源与投影不一致 | RuntimeFiles / artifact service | 相关 unit、真实 Cube / PostgreSQL / HTTP integration | 故意令来源与投影不同；恢复来源读取后字节断言失败 | Passed |
| 每次读取重新授权，缺失与非法文件明确拒绝 | 撤权、链接、超限、来源回退 | artifact service / filesystem | 当前授权与新增边界测试 | 保留撤权副本、删除投影、链接到其他目录或超过预算 | Passed |
| VM 挂载只读，持久预览不唤醒 VM | VM 文件系统与生命周期 | Cube provider / RuntimeFiles | 新增 Cube integration 回读文件字节和休眠状态 | 普通账号写入投影失败；HTTP 预览后原实例仍休眠 | Passed |
| 节点默认路径与模型路径职责清楚 | 部署与模型说明 | sandbox-operations / chat-widgets | 文档、源码及当前 Compose 挂载审阅 | 默认示例不依赖额外挂载白名单 | Inspected |

实际执行：

```bash
docker compose exec -T api uv run --group test pytest test/unit/services/test_artifact_service.py test/unit/sandbox/test_user_sandbox_backend.py test/unit/services/test_agent_artifacts_state.py -q -p no:cacheprovider
docker compose exec -T api uv run --group test pytest test/unit/workspace/test_fd_copy_consumers.py test/unit/services/skills/test_skill_edit_service.py -q -p no:cacheprovider
docker compose exec -T api uv run --group test pytest test/integration/sandbox/test_cube_file_preview.py test/integration/api/test_widget_sandbox_image_preview.py -q -p no:cacheprovider
docker compose exec -T api uv run --group test pytest test/e2e/test_cube_agent_execution_e2e.py -m e2e -q -p no:cacheprovider
docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q -o addopts=--tb=short -p no:cacheprovider
python3 scripts/verify_engineering_contracts.py
python3 -m unittest scripts.test_verify_engineering_contracts
cd docs && pnpm run build
git diff --check
```

相关 unit 分别 46、26 项通过，真实 VM / HTTP integration 2 项、确定性 Agent / worker / Cube E2E 1 项通过，工程契约及 66 项 verifier unit 通过。修改前选择来源与投影不一致、缺失投影和保存投影字节的 3 项测试均失败，分别观察到来源字节替代投影或未抛出不存在异常。新增真实测试只管理独立用户、VM、Thread 和 Skill。

全量后端 unit 首次执行到约 86% 以退出码 137 中断，期间 API 发生重启，未观察到 OOM；该次不计通过。完整重跑 2661 passed、61 skipped、7 subtests passed；61 项跳过保留其环境限定，不计产品通过。改动的 6 份 Python 文件 Ruff 检查和格式检查、文档构建与补丁空白检查通过；文档构建同时检查相对链接，保留已有大 chunk 提示。

不继承开发上下文的全新独立 Review 未发现阻断项。

未执行真实模型选择组件、浏览器 DOM、原生节点重启及长期共享 I/O 压力；本次不改变 UI、VM 模板或挂载协议，已有确定性 E2E 不替代这些范围。
