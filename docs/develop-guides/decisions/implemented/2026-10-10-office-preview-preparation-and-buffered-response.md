# 知识库文件预览提前生成与完整响应

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/knowledge_preview_service.py

## 问题

知识库 Office 文件首次点击时才转换，已有 PDF 缓存也会反复等待。已完整读取到内存的 PDF 经 BytesIO 同步流式响应按行迭代，约 200 KB 的文件产生数千个正文块。工作区还缺少 `.xlsx` 与 `.xls` 的 Office 预览识别。

目标是支持 Excel 原件预览、上传注册后在后台准备共享 PDF、缓存命中后完整返回，以及生成中自动显示和失败结束等待。聊天附件提前转换、存量文件批量补转、浏览器持久缓存、PDF 排版和登录导航不在范围内。

## 决策

### 实现方案

扩展现有 Office 格式识别到 `.xlsx` 与 `.xls`，复用 LibreOffice、30 MB 预览大小限制和转换超时。`.xlsm` 保持不支持。

原件注册后提交去重的 `knowledge_preview` Task。直接添加与上传后解析共用注册 service；PostgreSQL Task 拥有意图、lease 与终态，提交后投递现有 worker。worker 在发布 MinIO PDF 前核对 lease 与原件记录，原件与文档解析状态保持独立。预览意图提交异常记录带知识库与文件标识的告警，已提交的原件注册结果仍返回，解析与入库继续；后续缺失缓存读取补交任务。现成 PDF 对象拥有可读取结果。

工作区在授权后只读缓存；缺失时展示任务状态并补交存量文件的去重任务，失败或取消明确结束等待。已在内存的二进制通过完整 Response 和 Content-Length 返回。WorkspaceView 与 FileDetailModal 每两秒检查当前文件，切换、关闭和离开页面后隔离旧请求。FileDetailModal 的本地激活状态直接控制可见性，KeepAlive 离页即隐藏弹窗与遮罩，父组件的 open prop 延迟回传不影响隐藏。

## 替代方案

仅提前转换仍会保留缓存命中后的正文传输等待。同步上传等待转换会增加多文件处理时间。独立队列或浏览器持久缓存会新增执行状态或权限失效规则。复用现有 Task、转换器与共享缓存满足当前需求。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| XLSX 与真实 XLS 上传后在首次点击前生成对应 PDF，原件不变 | 只有格式识别或伪造成功状态 | Office 转换器、注册 service、worker、MinIO | `test/integration/api/test_knowledge_preview_http.py` 回读 Task、PDF 标记、原件哈希 | 损坏工作簿转换失败，缓存不发布 | Passed |
| 已有缓存完整返回且无需同步转换 | HTTP 成功但正文逐行阻塞或缓存重写 | Knowledge 预览模块、HTTP Response | `test/unit/services/test_binary_preview_response.py` 与真实 HTTP 重复读取 | 验收进程恢复旧 BytesIO 响应后正文分块断言失败 | Passed |
| 去重、授权、执行权与原件检查守住发布边界 | 并发重复任务、失权或无权限路径被成功伪装 | Task repository、权限依赖、预览 worker | service unit 与真实 HTTP 的并发、拒绝和最终对象断言 | 私有库、错误库、文件夹、失权、删除原件和存储错误 | Passed |
| 页面自动展示完成结果、错误结束等待、旧请求不覆盖新文件 | 永久 loading 或迟到结果覆盖 | WorkspaceView、file_preview | `web/test/unit/workspace_preview_polling.test.js`、`web/test/unit/file_detail_preview_polling.test.js` 与真实页面合成数据验证 | 失败、切换、deactivated、unmounted 和迟到响应 | Passed |

### 执行命令与观察边界

后端在匹配锁文件的离线运行镜像中只读挂载源码执行；验收服务为独立 PostgreSQL 数据库、专用 Redis、MinIO 与真实 worker。前端与文档使用锁文件对应的已有依赖。实际执行如下：

- `python -m pytest test/unit -m "not slow" -q -o addopts= --disable-warnings`：2547 passed，7 subtests passed。
- `python -m pytest test/integration/api/test_knowledge_preview_http.py --confcutdir=test/integration/api -m "not slow" -q -o addopts= -s`：1 passed；真实 HTTP、认证、Task、worker、LibreOffice 和 MinIO 字节回读。临时 trigger 只拒绝预览 Task 插入，上传和添加仍成功；删除 trigger 后首次读取补交并生成 PDF。
- `node --test --test-concurrency=1 "test/**/*.test.js" "test/**/*.spec.js"`：413 passed；详情轮询的 9 项用例执行提取的真实函数及 watcher/lifecycle 回调，属于 unit。
- `node node_modules/eslint/bin/eslint.js . --max-warnings=0` 与 `node node_modules/vite/bin/vite.js build`：Passed。
- Ruff 0.16.4 的 `check package`、`format package --check`，以及新增 service unit 与 HTTP 验收文件的 check/format：Passed。
- `python scripts/verify_engineering_contracts.py` 与 `python -m unittest scripts.test_verify_engineering_contracts`：Passed，后者 63 tests。
- 在 `docs/` 执行 `node node_modules/vitepress/bin/vitepress.js build`：Passed。
- 在仓库根目录执行 `git diff HEAD --check` 与 `git diff --cached --check`：Passed。

真实浏览器使用组件原始 Vue 实现和合成网络响应，覆盖生成中提示与完成后自动展示。真实 Vue KeepAlive 页面验证生成中离页关闭弹窗、请求计数停止、弹窗与遮罩的 DOM display 为 none，返回页面重新打开后自动显示 PDF。恢复旧可见性 getter 的独立测试进程保留陈旧 props.open=true，两条关闭断言因 visible=true 失败。浏览器合成数据验收和真实 HTTP/worker 验收是两条独立证据，不构成连接真实后端的浏览器 E2E。真实业务文件、其他浏览器和 PDF 排版视觉回归为 Not run。

恢复旧 BytesIO 逐行响应的测试进程产生 7102 个正文块，两条协议断言均因目标原因失败。恢复读取时同步转换后，读取边界测试因“不能在读取请求中转换”失败；缺少专用 Redis 或发现已有 worker 的 fixture 在写入前拒绝。XLSX 与真正 OLE 格式 XLS 均在首次点击前生成对应 PDF。

## 后果

提前转换占用现有 worker 槽位。文件记录与 Task 分开提交，进程崩溃造成的提交间隙由后续缺失缓存读取补交任务恢复。PostgreSQL 检查与 MinIO 发布不构成跨存储事务，删除竞态仍可留下无可读取元数据的派生对象。API 与 worker 需要部署一致的后端版本。

验证使用独立 PostgreSQL 数据库、显式指定的专用 Redis、MinIO、真实 HTTP 和 worker；fixture 在断言失败时也清理自身资源。该贡献不需要新增依赖、配置或 Schema 迁移。
