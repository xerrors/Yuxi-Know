# 知识文件作业终态刷新列表

状态：implemented
类型：bug-fix
Owner：frontend/src/modules/knowledge/model/knowledgeBase.js

## 问题

自动入库在上传、解析、索引之间存在不属于处理中的文件状态，文件统计也可暂时为零。文件轮询据此停止后，后台作业已经完成而页面仍显示待入库。用户同时要求合入已有共享 Skill 默认范围、Widget 图片标题样式和两份调研文档，只推 fork 的 develop/0-8-0。

## 决策

### 实现方案

复用后台作业 store 已有轮询，在注册已接受作业时允许登记一次终态回调；成功、失败和取消都通知调用方，重置登录会话时清理。分页未包含已登记作业时沿既有详情接口读取，不新增轮询器。知识文件提交绑定原账号和知识库，终态回调重新读取当前文件列表与统计；迟到的账号或知识库响应不得覆盖当前页面。同库请求按最新发出序号接收，分页快照更新后较早的元信息保留新文件和统计；最新背景请求完成也清理被取代的前景 loading。文件状态继续以服务端快照为准。

共享 Skill 仅在后端提供 global 允许范围时默认选择全局，个人安装和受限用户保留原契约。Widget 只调整标题样式。两份调研保留日期、源码基线及未验证范围，不作为 0.8 已实现功能。

## 替代方案

- 延长固定延迟或新增定时器：仍会被队列等待与阶段转换打断，复制作业轮询责任。
- 将 parsed/uploaded 永久算作处理中：普通上传与只解析也会无期限轮询。
- 只监听全部后台作业终态并刷新当前知识库：会把无关作业引入文件页面刷新。

## 验证

- `pnpm run lint:check`、`pnpm run test:unit`、`pnpm run build`：在独立验收 worktree 应用本变更后执行，通过；前端 641 项，typecheck 与生产构建通过。未混入同时编辑的 AgentPanel 文件。新增 loading 交叠断言另跑知识库 store 12 项通过。
- 三个相关 unit 文件 35 项通过。恢复旧 jobs/knowledge store 后，本次缺陷回归有 8 项失败；同库乱序响应由独立 Reviewer 另行复现，并验证修复后的 indexed / 70 与 loading 最终事实。
- Playwright Chromium 与独立生产镜像：通过。暂停验收 worker 后真实上传 Markdown 并勾选自动入库，恢复 worker 后原页面自行显示“已入库 / 28 Tokens”，期间未点击刷新或重载；SQL 回读为 indexed / 28。暂停期间新增文件尚未出现在列表，恢复后自动出现；中间 parsed / processing=0 的停止轮询窗口由 unit 精确覆盖。
- 生产浏览器上传合成 Skill ZIP：个人位置仍为初始选择；切到共享后读取范围默认全局、管理关闭；安装完成，SQL 回读 read_scope=global、manage_scope=null。受限范围与草稿不变由 unit 验证。
- WidgetImage 用实际 Vue 组件的独立浏览器 harness 验证 1440 与 390 宽度、浅深色，无横向溢出；实际 caption 为 11px、3px 8px、背景 alpha 0.4、blur 4px。截图保存在本地验收证据目录；此项为组件样式验收，未重新宣称完整会话图片上传链路通过。harness 的 favicon 404 与产品功能无关。
- 宿主后端 unit：2765 passed；生产 API 容器 unit：2703 passed、62 skipped（shipping 镜像无仓库根测试输入，宿主完整集合补齐），19 warnings。容器只补入 test 与 seed fixture，未修改 shipping 应用代码。

- `python3 scripts/verify_engineering_contracts.py`、84 项工程脚本测试、`pnpm --dir docs run build`（含站内链接检查）及 `git diff --check`：通过。

## 后果

真实外部知识连接器未联调，调研只保存已注明的观察基线。共享 Skill 默认全局是用户提供的行为变更，后端仍拥有最终安装与授权边界。
