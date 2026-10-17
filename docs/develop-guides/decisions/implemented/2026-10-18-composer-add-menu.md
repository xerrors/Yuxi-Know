# 输入区统一添加入口

状态：implemented
类型：feature
Owner：frontend/src/modules/session/ui/MessageInputComponent.vue

## 问题

「+」与 @ 分别提供上传和引用菜单，用户需要记住两套入口，资源候选的展示也不一致。

## 决策

### 实现方案

MessageInputComponent 统一拥有添加弹窗、资源候选及键盘导航。「+」记录当前插入范围并打开弹窗，@ 按查询过滤；顶部提供「上传附件」「添加图片」。上传动作交给 AgentInputArea，复用 SessionWorkspace 的附件弹窗和既有图片上传流程。原生图片选择器由 AgentInputArea 持有，选图后清空选择值，支持再次选择同一文件。

从 @ 选择上传只消费当前 @ 查询片段；点击「+」、关闭菜单和取消选图保留原正文。资源选择替换原查询或加号打开时保存的选择区。回答运行中保留菜单上传能力，disabled 状态拒绝添加。AttachmentOptionsComponent 的重复资源菜单已移除。

## 替代方案

保留两个菜单并各自补齐入口需要持续维护两套候选、头像和导航，因此使用同一弹窗。

## 后果

两个入口共享候选顺序与上传行为，资源头像沿用原实现。MessageInputComponent 拥有触发与查询片段消费，AgentInputArea 拥有文件选择和图片预览，上传限额、附件草稿归属和服务调用继续由现有流程拥有。

## 验证

- `frontend/test/browser/composerAddMenu.js` 使用真实 Vue 输入组件与原生文件选择器，断言两个入口项目一致、附件事件、正文选择区替换、取消选图、图片请求后预览、重复选择同一图片、运行中追加图片、键盘选择、无结果 Escape、disabled 和浅深色 1440/768px 布局。图片服务使用确定性 HTTP 响应，未验证真实后端上传存储。
- `docker compose exec frontend pnpm run test:unit`：696 项通过。
- `docker compose exec frontend pnpm run lint:check`、`docker compose exec frontend pnpm run build`、工程信任检查及其 66 项单测、`docs` 构建通过。
- 无真实登录会话，未执行登录后的完整发送链路；附件的跨 Thread 归属继续由既有测试负责。
