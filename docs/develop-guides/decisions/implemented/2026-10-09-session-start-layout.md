# 首次发送立即退出欢迎布局

状态：implemented
类型：bug-fix
Owner：frontend/src/modules/session/ui/SessionWorkspace.vue

## 问题

新会话发送时，工作区先创建线程并显示用户消息，读取 Input 快照后才同步会话路由。只用路由传入的新会话标记控制欢迎布局，会在首次发送期间同时显示消息、欢迎语和居中输入框。

## 决策

欢迎布局只在新会话路由且工作区没有线程时显示。已有线程的加载、空消息和等待首个回复均使用底部输入框。

### 实现方案

SessionWorkspace 用同一个派生状态控制输入框的 `start-screen` 类和欢迎语。线程创建成功后，当前线程身份立即使欢迎布局退出；提交接收后再同步会话路由，已接收 Input 的执行观察由共享 runtime 拥有。

## 替代方案

提前切换路由会改变首个输入恢复时序；用消息数量判断会让已有空线程和历史加载期间重新显示欢迎布局。线程身份直接表达是否进入会话，复用现有状态即可。

## 后果

附件上传创建线程时也退出欢迎布局，符合已有线程的页面语义。发送失败后的线程继续使用会话布局，返回新会话时恢复欢迎布局。

## 验证

`sessionWorkspaceVisibility.test.js` 复用同一视图片段，渲染路由标记、线程身份、历史加载和消息为空的组合，并验证线程创建和返回新会话的响应式切换。独立的 `chatStartScreen.test.js` 与重复派生状态 fixture 已删除。恢复仅依赖路由标记的缺陷会使已有线程的欢迎布局断言失败。

`sessionStartLayout.js` 在已登录开发页面暂缓实际发送，回读 DOM 和输入框边界，验证路由接管前用户消息出现、欢迎语消失且输入框底边位于视口底部；释放发送后验证会话路由、暗色窄屏的欢迎布局判断，并生成截图。结束时只停止本次创建的会话，等待归档边界允许清理并回读归档状态；失败时取消尚未投递的发送。该验证只证明布局切换，不证明整体窄屏体验和模型回复结果。

单测入口：`docker compose exec frontend node --test test/unit/sessionWorkspaceVisibility.test.js`，Passed。浏览器入口为 `playwright-cli -s=<session> run-code --filename=frontend/test/browser/sessionStartLayout.js`；其原有布局验收结果保留，本轮测试合并未重跑该依赖真实提交的脚本。
