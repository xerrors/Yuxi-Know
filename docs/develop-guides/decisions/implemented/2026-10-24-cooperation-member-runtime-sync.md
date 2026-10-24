# 协作成员复用唯一运行恢复入口

状态：implemented
类型：simplification
Owner：frontend/src/modules/session/model/sessionRuntime.js

## 问题

成员进入终态或人工等待后，运行订阅关闭。父会话再次提交输入、取消等待轮次或停止整树时，协作摘要仍会变化，已打开成员需要恢复持久详情。独立调用底层 stream 的摘要路径绕过共享恢复请求，又与异步终态收尾重复刷新历史，调用者无法等待一次完整恢复。Input 详情只证明该输入曾由某个 Turn/Run 消费；迟到的旧消费响应若直接启流，会取代已经恢复的新 Turn，而未变化的摘要无法发现这种倒退。

## 决策

### 实现方案

[根工作区](https://github.com/xerrors/Yuxi/blob/main/frontend/src/modules/session/ui/SessionWorkspace.vue)把有效协作摘要交给[共享 runtime](https://github.com/xerrors/Yuxi/blob/main/frontend/src/modules/session/model/sessionRuntime.js)，仅为已打开成员执行对账。摘要负责发现变化，Session、Turn、items 和 queue 接口拥有运行与内容事实。

所有运行恢复经 runtime 的同一入口按 Thread 合并。摘要使用 `fresh` 等待既有恢复结束后发起新读，拒绝复用摘要之前的快照。[运行订阅模块](https://github.com/xerrors/Yuxi/blob/main/frontend/src/modules/session/model/useAgentRunStream.js)的终态收尾返回可等待结果，完成唯一一次历史刷新后才报告成功；运行态恢复启动 SSE 后补读历史，不等待长连接结束。已读取的人工等待 Turn 直接供等待卡片恢复，不追加一次等待点查询。历史失败或运行版本变化返回失败，相同执行摘要继续重试。

[Input 观察者](https://github.com/xerrors/Yuxi/blob/main/frontend/src/modules/session/model/useAgentInputQueue.js)只合并该输入的正式 items 并移除相应乐观节点，消费事实通知 runtime 通过同一 `fresh` 入口回读当前持久 Turn。Input 的历史执行关联不拥有当前执行的选择权；同 Turn 的 steer 和恢复由当前 Turn 的 Run 归属决定。恢复失败时保留消费观察，下一次重试同一入口，不另建计时器或清除摘要去重记录。

摘要只有 `has_pending_input` 布尔值，无法区分同一轮追加的独立 Input。每次有效摘要都通过现有 queue 入口回读队列，执行详情只在摘要变化或恢复失败时重读。当前 Turn 改变时关闭旧 SSE，重复视图仍共享一个订阅。

[摘要观察者](https://github.com/xerrors/Yuxi/blob/main/frontend/src/modules/session/model/useSessionCooperation.js)沿用已有周期。根工作区和浏览器后台停止摘要轮询，重新显示后立即刷新。隐藏成员更新共享事实时，视图继续约束焦点、滚动和已读副作用。

## 替代方案

- 保留摘要对底层 stream 的独立调用并追加等待：恢复入口仍分裂，终态历史仍由两个调用者争相补齐。
- 为成员保留永久 SSE：需要改变跨轮次事件路由、订阅和重连生命周期，超出当前职责收拢范围。
- 每个成员增加定时读取：重复已有根摘要观察职责，请求数随视图增长。
- 仅按执行摘要变化刷新队列：已有 pending Input 时追加第二条输入，布尔摘要不变，队列节点无法出现。
- 在每个 Input 响应增加版本 guard：较新执行会让合法的旧 Input 消费事实被丢弃，仍保留队列与恢复入口争夺当前执行的问题。

## 后果

恢复 Promise 的成功结果包含本次需要的持久历史，不再只表示执行标志已写入。终态历史失败仍保留已接收的流输出；迟到收尾不能清理新执行的订阅。详情读取量取决于已观察成员数量，不读取未打开成员，普通单会话不增加摘要驱动的读取。

## 验证

[组合单测](https://github.com/xerrors/Yuxi/blob/main/frontend/test/unit/sessionCooperationSync.test.js)覆盖单次终态 items 读取、终态历史延迟和失败、终态及运行态版本冲突重试、摘要前在途恢复、外部取消、新轮次、同摘要新 Input、旧 SSE 替换和页面失活。[消费交错回归](https://github.com/xerrors/Yuxi/blob/main/frontend/test/unit/sessionInputConsumption.test.js)用显式延迟响应覆盖旧 Input 迟到、FIFO 推进、同 Turn 新 Run、消费前已终态和消费前在途恢复。恢复 Input 直接启流会让当前 Turn、Run 和唯一 SSE 断言失败；消费 items 继续保留自身执行归属。恢复独立终态补读会让 items 次数断言失败；历史失败仍记成功或移除版本检查，会让相同摘要重试后的内容断言失败。

[真实页面协议 fixture](https://github.com/xerrors/Yuxi/blob/main/frontend/test/browser/cooperationMemberSync.js)验证等待卡片移除、输入恢复、暂停队列、同摘要第二条 Input、新轮次历史、唯一 SSE、旧 Input 消费响应在新 Turn 订阅后返回、隐藏成员不标已读或切换标签，以及浏览器后台停止摘要轮询。初始无 SSE 的等待态结束前台读取后再进入后台阶段，避免把已开始请求的迟到结果误算为后台发起。截图覆盖浅色、深色和 375px 页面；证据只证明前端装配，不替代 worker E2E。

实际命令：

```bash
cd frontend
node --test --test-concurrency=1 test/unit/sessionInputConsumption.test.js test/unit/sessionCooperationSync.test.js test/unit/sessionRuntime.test.js test/unit/agentRunEvents.test.js test/unit/sessionCooperation.test.js test/unit/agentInputQueue.test.js test/unit/sessionWorkspaceVisibility.test.js
cd ..
docker compose exec -T frontend pnpm run lint:check
docker compose exec -T frontend pnpm run test:unit
docker compose exec -T frontend pnpm run build
playwright-cli -s=coop-input-owner run-code --filename=frontend/test/browser/cooperationMemberSync.js
```

相关单测 80 项、全量前端 unit 849 项、lint、类型检查、构建和真实页面协议 fixture 通过。Input 直接启流的负控在旧 Turn、同 Turn 旧 Run 和已终态轮次三条回归中失败。真实 worker 驱动的浏览器链路为 Not run；后端事件与持久状态的实际组合仍由后端 E2E 独立验证。

旧能力不存在：协作摘要不再直接调用底层 stream 恢复，不再独立补第二次终态历史读取；Input 观察者不调用 `startRunStream` 或重置当前执行。

重新引入条件：出现无法由现有 Thread 恢复入口表达的独立产品协议时，另行说明 Owner 和验证。
