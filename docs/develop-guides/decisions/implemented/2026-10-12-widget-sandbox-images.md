# 沙盒图片由对话组件展示

状态：implemented
类型：simplification
Owner：frontend/src/shared/ui/WidgetImage.vue

## 问题

交付物图片类型与 chat-widgets Image 重复表达图片展示，专用交付物尺寸和分组增加维护面。Image 直接把沙盒路径交给浏览器无法读取持久文件，强制 Card 根节点使单张图片带有多余外框和标题区，多张图片也缺少直接分组协议。

## 决策

### 实现方案

present_artifacts 恢复路径列表登记，删除 type 参数、图片分组与尺寸样式。state reducer 与前端路径归一化继续提取旧 checkpoint 对象的 path。Image.path 支持沙盒虚拟绝对路径，src 继续表示 HTTPS/同源 URL，二者互斥，会话层将带当前 Thread 身份的既有 artifact 预览 API 作为读取能力传给固定组件。后端继续拥有 Thread 授权、用户路径与 no-follow 文件边界、预览预算；无需提前登记交付物或新增公开接口。组件只接受图片响应，切换来源或会话及卸载时释放 Blob URL，旧请求不得发布结果。MarkdownPreview 将既有同源受保护图片 URL 白名单和 apiGet 作为 source 读取能力注入组件；组件及预览统一拥有同源图片鉴权和 Blob 生命周期。Markdown 图片增强只处理围栏外的普通图片，避免双重请求。公开 HTTPS 和同源静态图片直接由浏览器读取。Image 和 ImageGroup 支持直接作为根节点；单图默认铺满正文宽度并保留原始比例，移除外框、阴影与标题区。可选 caption 以半透明胶囊标签叠放在图片左下角，详细说明放围栏外。chat-widgets Skill 明确要求多图请求只输出一个 ImageGroup、每张图只放一个 Image，不逐图套 Card；图片回复保持简短并把围栏直接放在对话正文。前端按模型输出结构渲染，不猜测或改写模型意图。ImageGroup 只包含 Image，使用统一5:4、cover缩略图横向滑动，不显示滚动条或数量角标。每张图保留独立加载和失败状态，点击后在既有 Ant Modal 的全屏预览中查看完整图片；沿用 Yuxi 浅深主题，居中适应视口，两侧箭头切换、右上关闭、底部简短说明，无左上菜单或卡片标题区，支持方向键、Esc和关闭后的焦点恢复。沙盒图片预览通过同一会话读取能力重新授权；受保护的同源URL预览通过同一读取能力鉴权，不依赖缩略图打开时的加载状态。整行可点击列表项中的图片不创建嵌套预览控件。组件的其他协议仍由[chat-widgets 决策](./2026-10-12-chat-widgets.md)维护。

## 替代方案

- 图片始终放在 Card 内：强制外框和标题区，不符合单图展示与图片组需求。

- 保留交付物图片展示：与用户要求冲突，继续维护重复布局。
- 新增 widget 图片接口：重复当前已支持授权文件预览的用例。
- 直接将沙盒路径或带 Token 的地址写入 img：浏览器无法访问沙盒，凭据进入内容。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 交付物仅登记路径并展示文件卡片，旧对象保留路径 | tool/checkpoint/历史 | present_artifacts/state/messageProcessor | 相关后端与前端 unit | 旧 image 对象不触发图片预览 | Passed |
| 沙盒图片经当前会话鉴权读取 | 文件/HTTP/DOM | artifact service/会话层/Image | HTTP integration 与浏览器 | 越权、路径跳转、非图片响应拒绝 | Passed |
| 单图直接展示与胶囊短语，图片组无滚动条和数量角标 | 协议/DOM/布局 | parser/WidgetNode/WidgetImage | 前端 unit 与浏览器 | 非图片成员拒绝、窄屏仍可横向浏览 | Passed |
| 全屏预览能切换且键盘可用 | 交互/授权/资源 | WidgetNode/WidgetRenderer/WidgetImage | 浏览器实际点击、方向键与焦点回读 | 未加载/失败/非交互图片不打开预览，切换会话关闭预览 | Passed |
| 切换与卸载释放图片且不接受旧响应 | 生命周期 | WidgetImage | 前端 unit/浏览器 | 延迟旧请求不能覆盖新图 | Passed |

旧能力不存在：工具 schema 和新 state 不含图片展示类型，前端没有交付物图片分组与专用尺寸适配。

重新引入条件：有无法通过固定 Image 组件满足的明确交付物消费需求，并重新评估协议与长期维护成本。

## 后果

VM Home 或临时目录中的图片先保存到当前 Project 工作目录再展示；模型使用工具返回的真实沙盒路径。持久文件读取与部署约定由[用户投影一致性决定](./2026-10-16-runtime-file-projection-consistency.md)维护。历史 tool 调用中的 type 被忽略，历史图片按文件卡片读取。真实模型选用组件受 Skill discovery 影响，确定性验证只证明渲染链路。

执行验证：

```bash
docker compose exec -T api uv run --group test pytest test/unit/services/test_agent_artifacts_state.py test/unit/services/test_checkpoint_state_reader.py -q
docker compose exec -T api uv run --group test pytest test/integration/api/test_widget_sandbox_image_preview.py -q
docker compose exec -T api uv run --group test pytest test/unit -m 'not slow' -q
docker compose exec -T frontend pnpm run lint:check
docker compose exec -T frontend pnpm run test:unit
docker compose exec -T frontend pnpm run build
playwright-cli -s=<logged-in-session> run-code --filename=frontend/test/browser/widgetSandboxImages.js
backend/.venv/bin/ruff check <changed-python-files>
backend/.venv/bin/ruff format <changed-python-files> --check
python3 scripts/verify_engineering_contracts.py
python3 -m unittest scripts.test_verify_engineering_contracts
cd docs && pnpm run build
git diff --check
```

相关后端 unit 17 passed；图片 HTTP integration 1 passed。后端全量 unit 2724 passed、60 skipped，前端 unit 578 passed，lint、typecheck/build、工程契约与 64 项 verifier unit、文档 build 通过。容器缺少 Ruff，改用工作区已有 Ruff，改动的 Python 文件 lint 与格式检查通过。

浏览器验证使用真实上传文件、实际 ReferenceAnnotatedAnswer/MarkdownPreview/Image 组件和鉴权 API。单图原始尺寸640×360，浅深主题在1440/1024/768/375px页面分别铺满可用宽度，保持16:9且正文不溢出。caption胶囊距图片左边和底边各10px。7张图片的图片组在1024px下缩略图320×256，768px下约234.66×187.73，375px下120×96，均为5:4、cover、同高同排；组内可横向滚动，正文不溢出。滚动条及数量角标均隐藏，浏览器样式和DOM回读通过。已加载与延迟加载缩略图在375px下均保持96px高度；恢复160px通用加载占位时，浏览器因高度[96,160]不一致而失败。

点击第三张打开图片3/7，下一张、方向键回到上一张、Esc关闭和图片焦点恢复通过。浏览器用延迟响应验证受保护src的缩略图、完整预览和先打开再切换到未就绪图片的场景：请求均通过鉴权fetch，原生未鉴权图片请求为零。前端unit证明普通src不随沙盒loader切换而重置加载状态、非图片响应及未加载/失败/非交互图片的预览拒绝。回复卸载重建、Blob释放、缺失文件、无权Thread和旧image artifact仅按文件展示继续通过。

截图由浏览器探针生成到临时目录，构建产物与截图不提交。

checkpoint HTTP 回归命令的业务断言为 2 passed，但共享清理 fixture 拒绝已有重叠 Workdir，整条命令为 error，不能计为全套通过。新增图片 HTTP 测试只管理自己创建的资源并独立通过。真实模型生成并选择 widget、完整已持久化回复在会话页面自然回读未验证；浏览器验证覆盖实际渲染链路与同内容重建。

`docker compose exec -T api uv run --group test pytest test/e2e/test_agent_lifecycle_e2e.py::test_attachment_survives_run_runtime_recreation -m e2e -q` 在共享清理 fixture 阶段被同一已有重叠 Workdir 拒绝，1 error，未进入业务执行。沙盒重建与完整 worker 生命周期不计通过；图片展示的真实文件/HTTP/DOM 链路由独立图片 integration 与浏览器探针覆盖。

全屏预览在1024×900铺满视口，375×812保留完整图片和可触达侧边箭头；浅深主题截图检查通过。图片预览具有可访问名称，关闭按钮、Esc、方向键、焦点恢复与受保护图片鉴权读取通过。移除无显式比例图片加载时的160px最小占位，改用紧凑状态提示；此占位调整未复现用户原始流式消息，不能据此确认截图空白的原始原因。
