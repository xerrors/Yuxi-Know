# 对话组件的图文组合与表单回答

状态：implemented
类型：feature
Owner：frontend/src/shared/lib/chatWidgets.js

## 问题

图片展示优先的要求被 Skill 扩大为禁止图片进入 Card、Row、Col，导致有说明需求的图文组合无法自然使用。用户还需要在对话中填写少量文本、单选和日期，并提交答案让模型继续工作。

## 决策

### 实现方案

内置 chat-widgets Skill 按展示目的选择现有布局：纯图片使用独立 Image/ImageGroup，图文内容允许 Image 与 Card、Row、Col 组合，分类比较继续使用 Chart。引导聚焦信息层次和具体例子，不扩展检索、摘要或推荐续聊的场景体系，不改变按需发现机制。

chatWidgets.js 拥有模型 JSON 的有限协议校验，WidgetNode 拥有 Form、Input、Textarea、RadioGroup、DatePicker 和 Button 的原生表单渲染。Button 的 submit、label、style、variant 等沿用 ChatKit 命名；Form 的 onSubmitAction 和 Button 的 onClickAction 只开放固定的 send_message 动作，payload.text 表达提交目的。表单字段由 name 标识，label 持续可见，浏览器先验证必填和日期范围，再收集回答。

WidgetRenderer 等待会话动作回调确认接收，并显示提交中、失败和已发送反馈。SessionWorkspace 将回答作为独立普通用户消息交给现有 sessionInput，不携带或清空编辑器的草稿、图片和附件；失败复用现有请求身份和重试。输入接收回调同时通知原组件，因此通过会话入口重试成功也会消除原表单的失败提示。未知服务端动作、嵌套表单、重名字段与交互嵌套在模型边界拒绝。生成期和无法接收消息时只读。组件不直接执行工具或业务写入，不新增 API 或持久状态。

逐节点流式呈现本轮不实现；完整围栏闭合后展示。

表单的桌面宽度、字段网格与紧凑引导由[对话表单的桌面宽度与字段排布](2026-10-17-widget-desktop-form-layout.md)补充。

## 替代方案

- 填入草稿后再次发送：用户明确选择提交即发送。
- 接入完整 ChatKit action 后端：扩大当前输入收集需求，不采用。
- 只补 Skill、保持图片组合禁令或无提交表单：不能满足图文与填写需求。

## 后果

表单回答遵循普通消息的接收、幂等重试和持久历史；数据不另存为业务表单。未提交内容和已发送反馈属于当前挂载实例，刷新以会话中的用户消息为准。协议只对齐本次使用的 ChatKit 字段，不承诺完整 SDK 兼容，任意服务端动作不开放。原生表单校验使用原型方法，字段名 reportValidity 不会遮蔽提交入口。

真实模型的按需发现和协议输出仍受模型行为影响；本次真实样本不证明所有模型的稳定性。图文、表单及普通用户消息的归属与资源授权继续由原链路拥有。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 纯图片优先，图文可组合，Skill 实际生效 | 模型发现及最终输出 | chat-widgets/SKILL.md | 浏览器普通提问、实际 read_file 结果中的 2026.10.17 版本及最终 DOM | 两张图片为一个 ImageGroup 且没有 Card，图文实际组合 Card/Row/Col/Image | Passed |
| 表单能收集文本、单选、日期并发送 | 模型 JSON、原生 DOM、会话输入 | chatWidgets/WidgetNode/SessionWorkspace | 专项 unit、浏览器填写与刷新后用户消息和模型答复 | 空必填、日期越界、纯空格；未知动作、嵌套表单、重名字段、方法名遮蔽 | Passed |
| 发送保留编辑器草稿和附件 | 提交快照 | SessionWorkspace/sessionInput | 专项 unit 核对独立快照；浏览器核对草稿保留 | 表单快照附件为空，普通发送仍携带附件 | Passed |
| 主题、窄屏与状态可用 | CSS、交互生命周期 | WidgetRenderer/WidgetNode | lint/unit/build，真实明暗主题、1440/1024/768/375px DOM 和截图 | 空输入未发送，断网失败保留字段，重试成功原卡片已发送，卡片无横向溢出 | Passed |

浏览器使用 Playwright CLI 的 widget-forms 会话，通过真实页面提问、点击、填写和刷新；没有手工调用业务 API、拦截模型响应或向历史注入组件。技能管理页显示更新后的说明；实际模型工具详情展示 `/home/user/skills/chat-widgets/SKILL.md` 的读取结果及版本，最终表单和图文包含新增能力。

真实问题覆盖“直接展示两张图片，横向浏览”“图在左、标题与三点说明在右”“填写周末出游条件”“活动报名表，日期限定在十一月”和独立说明按钮。两张图片实际解码为 640px；图文含对应三点说明。活动表单提交后，普通用户消息和模型确认逐项包含称呼、日期、单选标签及备注。浏览器断网后，使用现有“重试发送”入口，原卡片显示已发送，只增加一条回答消息，独立草稿保持原文。附件隔离由提交快照 unit 验证，本次真实页面没有上传附件。

普通桌面会话在 1440×1000 验证“同一张表填写工作坊主题、日期、形式、参加对象及补充说明，提交后生成150字以内通知”。浏览器实际填写并提交后，公开用户消息逐项保留全部字段，最终通知正文独立计数为118字，包含主题、日期、线下、对象、时间、地点及携带要求。完整视口截图覆盖用户任务、表单填写和提交后的回答，截图没有裁切为独立组件。

自然触发的观察边界：两个未提表单的任务（收集团建条件、收集信息后写邀请通知）均使用已有 ask_user_question；“可填写的需求单”也进入该工具。本次只有明确要求同一张对话表单、一次填写的通知任务触发新 Form。既有工具描述覆盖偏好与需求补充，与组件 Skill 的信息收集用途重叠；这些样本未证明自然信息收集会主动选择新 Form。自然通知任务完成逐题回答后能生成通知，该结果不计为 chat-widgets Form 通过。单独询问日期的样本也走既有提问工具，不计为新 Form 的触发证据。

明暗表单与图文在 1440、1024、768 和 375px 检查布局。原生日期输入使用浏览器本地化显示，发送值保持 YYYY-MM-DD。完整暗色表单与窄屏截图均核对实际颜色、字段和可见范围；截图及原始会话保留在本地，不提交运行产物。原生方法遮蔽有专项回归，恢复旧调用方式会因同名字段覆盖方法而失败。

实际检查结果：

| 命令 | 结果 |
|---|---|
| `docker compose exec -T frontend node --test test/unit/widgetSubmission.test.js test/unit/widgetForms.test.js` | Passed，31 tests；含重试反馈与原生方法遮蔽回归 |
| `docker compose exec -T frontend pnpm run test:unit` | Passed，692 tests |
| `docker compose exec -T frontend pnpm run lint:check` | Passed |
| `docker compose exec -T frontend pnpm run build` | Passed，含 typecheck |
| `docker compose exec -T api uv run --group test pytest test/unit -m "not slow"` | Passed，2720 passed、62 skipped、7 subtests；skip 不计为能力通过 |
| `python3 scripts/verify_engineering_contracts.py` | Passed，216 decisions |
| `python3 -m unittest scripts.test_verify_engineering_contracts` | Passed，66 tests |
| docs：`pnpm run build` | Passed，包含相对链接检查 |
| `git diff --check` | Passed |

前端及文档构建保留 bundle 大小提示；后端有现有依赖弃用和缓存目录权限警告。开发浏览器的语法高亮依赖存在加载警告，不影响本次组件结果；本次没有修复这些独立问题。真实模型验证只覆盖上述样本，附件隔离未做真实上传，未验证所有模型输出稳定性或完整 ChatKit SDK 兼容。
