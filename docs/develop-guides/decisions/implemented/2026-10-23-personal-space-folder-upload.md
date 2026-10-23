# 个人空间文件夹上传

状态：implemented
类型：feature
Owner：backend/yuxi/modules/workspace/services/files.py

## 问题

事实：改动前的个人空间上传入口只接受普通多选文件；前端输入框没有 `webkitdirectory`，API 只发送 `parent_path + files`，服务层用 `Path(file.filename).name` 把客户端文件名压成单段并拒绝同批重名（`frontend/src/pages/WorkspaceView.vue`、`frontend/src/apis/workspace_api.js`、`backend/yuxi/modules/workspace/services/files.py`，HEAD 版本）。知识库在 `462bb204` 单独实现了目录上传，通过 `webkitRelativePath` 和 `source_paths` 保留层级；个人空间没有跟进。仓库中没有找到个人空间文件夹上传的既决或否决记录。推断：个人空间未跟进知识库的目录上传，是两套上传链路造成的能力缺口，而不是已记录的技术限制。

## 决策

### 实现方案

后端语义 Owner 是 `files.py`：路由接收可选的 `relative_paths`，service 负责逐段校验、目标去重、写入前冲突预检和失败回滚；父目录创建继续复用 `Workspace` 的 no-follow `create_parents` 路径。前端 Owner 是 `WorkspaceView.vue`：独立目录输入、`workspaceFolderUpload` 模型负责收集与分批、`workspace_api.js` 负责字段编码。普通上传不传 `relative_paths` 时走原分支。

- `/api/workspace/upload` 增加可选的 `relative_paths` 表单字段，按顺序与 `files` 对齐。目标路径为 `parent_path + relative_path`，保留浏览器给出的根文件夹名。未提供该字段时保持原有扁平上传行为。
- 服务端逐段校验相对路径，拒绝绝对路径、`..`/`.`、空段、反斜杠、NUL、Windows 盘符开头和越界路径；每个段复用现有 `validate_directory_name`。前导空白属于真实名称，前后端均不裁剪相对路径。尾随空白组件返回明确的 422：通用 Workspace scope 会裁掉路径末尾空白，目录单独寻址同样受影响，上传不能静默改名或创建无法浏览的目录。目标路径中间出现符号链接或普通文件时返回 4xx，不写入。
- 完整虚拟路径（含 `parent_path`）最多 64 段；单个组件最多 255 UTF-8 字节；相对路径字段本身最多 4096 UTF-8 字节（不含工作区根前缀；完整 OS 路径超长仍由预检映射为 422）。深度上限覆盖父目录累积，避免新入口把树推进到既有递归删除会 `RecursionError` 的深度。
- 写入前检查所有目标是否已存在或类型冲突，冲突时整批不落盘；同批任一文件路径同时是另一目标的祖先时，也在写入前拒绝，与文件顺序无关。目录可复用合并，已有文件不覆盖；批次写入中途失败时沿用现有语义，删除本批已写文件，已创建的空目录保留。
- 前端新增“上传文件夹”入口和独立 `input[webkitdirectory]`，从 `webkitRelativePath` 构造相对路径。按每批最多 50 个文件、18 MB 顺序上传；单个超过 18 MB 的文件独立成批，因此“单批低于 20M”不是绝对保证，超过 20 MB 的单文件仍会 413。跨批允许部分成功，界面报告已上传数量和首个失败批次。
- 隐藏文件按浏览器 `FileList` 原样上传。浏览器不会把空目录放进 `FileList`，本次不引入 File System Access API；前端在 `change` 事件得到空 `FileList` 时提示空目录不会被上传（真实 OS 选择器是否对空根目录触发 `change` 未验证）。
- 不修改知识库上传、拖拽文件夹、CLI、目录下载或通用上传框架；不调整 nginx 限制。单文件超过 20 MB 在自带 nginx 拓扑下仍会 413，这是既有入口约束。

## 替代方案

- 前端组合现有 `createWorkspaceDirectory` + `uploadWorkspaceFiles`，按目录多次调用。后端零改动，但目录创建接口无法区分“已有目录”和“已有文件”，合并语义需要额外读取且存在竞态；请求数、错误语义和跨请求回滚都更弱，因此未采用。
- 把完整相对路径塞进 multipart filename，由服务端解析。依赖框架对 filename 的处理，隐式且不可控，未采用。
- 已有文件跳过或覆盖。跳过需要新增响应字段和跨批过滤语义；覆盖会改变现有不覆盖契约，两者都超出本次最小范围。
- 为 `/api/workspace/upload` 单独放宽 nginx 到 100 MB。会改变生产入口的上传面，属于独立的部署与安全决策；本次保持 20M 并记录单文件限制。
- 用 `showDirectoryPicker` 保留空目录。跨浏览器支持有限，且需要另一套目录选择和提交路径，明显扩大范围。
- 为支持尾随空白名称而修改所有 Workspace scope 规范化及其调用方。影响个人空间之外的既有路径契约；上传边界明确拒绝更小，也避免静默损坏名称。

## 后果

- `relative_paths` 是可选字段，普通多文件上传在通常路径下保持原行为；完整路径深度上限同样适用于 flat 上传，向 64 段及以上父目录上传会返回 422，这是有意收紧。
- 非法相对路径（含过深层级、超长组件、尾随空白组件）返回 422；目标已存在、目标类型冲突、目标中间组件是符号链接返回 400；`parent_path` 不存在返回 404、存在但不是目录返回 400、符号链接/权限或中间组件错误返回 403。前端对 400/413 提供批次路径和重试提示。
- 开发 API 的 Compose 命令不带自动重载，修改路由或 service 后需要重启 API。旧进程的上传路由忽略未知 `relative_paths` 字段，会把新前端的文件夹请求按普通文件平铺；源码挂载不代表运行中的路由已更新。
- 每批写入前最多增加 50 次目标 stat；换来冲突在写入前被发现，减少半批文件和空目录残留。
- 跨批没有原子性：前面已成功的批次保留，界面明确显示“已上传 N 个文件”。同一批次内仍沿用后端回滚文件的行为。跨批部分成功后重新选择同一根文件夹会因已有文件再次 400；用户需要删除已上传文件后重选整个根文件夹，直接选择子目录会改变目标层级，本次不实现 skip-existing。
- 隐藏文件（包括 `.git`、`.DS_Store` 等）会按原样计数和上传，可能快速消耗 50 文件/18 MB 批次预算。
- 空目录不会被上传；这是 `webkitdirectory` 在 Chromium 中的行为（其他目标浏览器未验证），不是后端丢弃。单文件超过 20 MB 在自带 nginx 拓扑下仍不可用。
- 既有 `create_workspace_directory` 仍可逐层创建超过 64 段的目录；本次上传入口拒绝继续加深，但删除递归本身仍是既有实现，不在本次修改。

## 验证

- Passed：后端相关 unit 68 项，覆盖 multipart 字段与文件顺序、目录与字节保留、合法前导空白、尾随空白拒绝、同批祖先冲突的两种顺序、既有文件不覆盖、路径隔离及长度/数量上限。前导空白及尾随空白回归测试在修复前 4 项失败，修复后通过。
- Passed：真实 HTTP integration 30 项。除了既有路径、冲突和权限边界，根目录列表明确验证上传产物是目录，51 文件分两请求后回读完整文件集合和每份字节；中文与前导空白名称能继续浏览并下载；不合法名称及同批祖先冲突不留下目录。
- Passed：前端定向测试 30 项，包含原始相对路径、数量/字节切批、菜单语义、真实 FormData 字段/文件顺序/Blob 字节与普通上传兼容。前导空白回归在修复前失败，修复后通过。
- Passed：Chromium 真实页面选择目录，53 文件按 50 + 3 两批请求上传。根目录在列表中显示为文件夹，51 个子目录中的同名文件、根文件与隐藏文件共 53 份下载字节全部匹配；进入嵌套目录可见对应文件。空目录不上传。另一组 51 文件的末批目标预先存在时，真实页面显示已上传 50 个文件、第 2/2 批失败；回读前批 50 份字节匹配，冲突文件保留原字节。前导空白名称可下载，尾随空白名称显示具体拒绝原因。
- Passed：前端全量 unit 803 项、`pnpm run lint:check` 和 `pnpm run build`；后端全量 `pytest test/unit -m "not slow" -q` 3100 passed、107 skipped；`yuxi` 全目录 Ruff check/format/import 排序；工程契约检查及其 66 项单测、docs build 和 `git diff --check`。
- Inspected：Compose 的 API 命令不带 `--reload`。运行中的旧路由曾不声明 `relative_paths`，实际上传产物是根下的散落文件；重启开发 API 后 OpenAPI 声明该字段，同一文件夹能保留根与嵌套目录。此验证直接读取协议及目录结果，不能用单元测试替代。
- Not run：真实 100 MB 单文件 HTTP、非 Chromium 浏览器、客户端符号链接展开、真实 OS 空目录选择是否触发 `change`。自带 nginx 的 20M 上限仍由部署配置拥有；未重新执行入口大文件探针。

实际定向命令为 `pytest test/unit/services/test_workspace_service.py test/unit/routers/test_upload_boundary.py -q`、`pytest test/integration/api/test_workspace_folder_upload_api.py -q` 与 `node --test test/unit/workspaceFolderUpload.test.js test/unit/workspace_action_semantics.test.js test/unit/api_boundary.test.js`；后端命令在 Compose API 容器内通过 `uv run --no-sync --group test` 执行，前端命令在 `frontend/` 执行。完整测试层级见[测试规范](../../testing-guidelines.md)。
