# 对话组件、按需 Skill 与真实模型输出

状态：implemented
类型：feature
Owner：frontend/src/shared/lib/chatWidgets.js

## 问题

用户需要模型在普通对话中生成卡片、图表、图片、推荐列表和短表单，直接在正式回复中使用。仅展示表单或预置聊天示例不能证明真实模型调用和业务数据来源；完整说明默认预加载增加首轮上下文，用户要求按需 Skill 加载。

## 决策

### 实现方案

内置 `chat-widgets` 的描述覆盖分类比较、时间趋势、图文介绍和推荐选择。正文维护有限协议、完整跨行示例和最终回复约束，模型通过既有 Skill discovery/read_file 按需读取。ChatBotContext 继承 BaseContext 的空预加载默认值，不增加组件特例、关键词路由或模型输出改写。显式 Skills 允许列表需要包含该 Skill；默认全部选择沿既有授权归一化发现能力。

`chatWidgets.js` 在模型 JSON 边界校验19种有限节点、受限呈现属性和 compose 动作，根为 Card 或 ListView。`WidgetRenderer.vue`、`WidgetNode.vue` 使用 Vue 文本插值和固定样式映射；非法 JSON、未知属性和服务端动作显示诊断及原始内容，未闭合围栏显示生成状态。限制为24000字符、100节点、8层，字段和选项唯一，整行列表禁止嵌套交互控件；不接收任意 HTML、CSS、脚本或图表配置。

`WidgetChart.vue` 复用现有 ECharts 的 SVG renderer，支持有限 data/series/xAxis、柱状与折线、图例、悬停数值、可展开数据表、零/负值及空数据。组件拥有 resize/dispose、主题重绘与本地图例状态。`WidgetImage.vue` 使用原生 img，提供加载/失败/恢复状态；受保护图片沿已有 Markdown 鉴权请求加载。Markdown 拥有 blob URL 生命周期，复用仍挂载的资源，移除或卸载时释放。

`MarkdownPreview.vue` 在正式聊天显式启用时挂载组件，相同 JSON 与闭合状态的 DOM 在正文追加、主题和行号变化时复用，保留字段值；定义改变后重建。JSON 保留原始文本，弯引号修复只作用于围栏外；引用行定位沿原 Markdown Owner。`SessionWorkspace.vue` 经普通消息和折叠过程组传递 compose 动作，将可见标签、值和动作文字追加到草稿并聚焦，用户发送后走既有 Input 链路。整组生成期间控件只读，较早闭合消息也遵循该边界。

组件属于 Turn 的 result_run_id 指向的最终公开 Message，刷新由历史恢复。Skill 要求完成查询及工具调用后，在最终回复保留完整组件；不把过程图表移入最终答案，不从相邻 Run 或前端预置数据补结果。天气等时效请求必须实际取数；搜索失败可以沿既有只读网络查询和审批协议更换公开来源，全部渠道失败则说明缺失，不生成假天气。逐日极值优先使用 daily 字段，小时采样使用采样标签；日期、单位、来源 URL 与文字解释分别核对。

浅色使用白色卡片、细边框和轻阴影，深色使用炭灰卡片、更深字段和更亮主动作，复用 Yuxi 语义颜色、字体和全局主题。公开示例页、示例数据与本次新增专项测试脚本不属于交付；使用入口为普通 Agent 对话，方法由[Skills 管理](../../../agents/skills-management.md#对话组件-skill)拥有。对话 HTML Preview 的移除由[对应决定](2026-10-12-remove-inline-html-preview.md)维护。

## 与 ChatKit 的差异

参照官方 [Widgets](https://developers.openai.com/api/docs/guides/chatkit-widgets)、[Actions](https://developers.openai.com/api/docs/guides/chatkit-actions)、[Themes](https://developers.openai.com/api/docs/guides/chatkit-themes) 及其 Widget Builder。使用频率没有遥测，分类比较、时间趋势、图文和推荐选择按用户明确需求纳入基础能力。

| 场景 | Yuxi 的对应能力与差异 |
|---|---|
| 摘要与推荐列表 | 布局、字号、标签、图标、按钮变体和整行键盘动作；沿用 Yuxi 色彩字体，不承诺像素级复制 |
| 图表 | bar/line、真实图例/悬停、响应式及双主题，补充数据表；area、堆叠、任意坐标和自定义颜色未实现 |
| 图片 | HTTPS/同源src、alt、cover/contain、宽高比、固定圆角与加载恢复；图片上传、放大及完整尺寸协议未实现 |
| 短表单 | 原生 Input/Select/Textarea、可见标签和必填校验；弹层随平台，字段收集到草稿 |
| 双主题与布局 | 跟随全局主题，有限尺寸/间距枚举；没有独立组件theme、任意CSS或Card根级确认配置 |
| 动作与流式 | compose草稿、生成期只读、闭合后显示；没有服务端action、自动发送或逐节点流式更新 |

## 替代方案

- 完整 ChatKit SDK：需要适配 Vue、会话协议与持久化，现有消费者需要有限子集。
- 静态 HTML、前端固定示例或响应拦截：无法证明真实 Skill、取数和最终回复，也不能覆盖实际动作。
- 默认预加载组件或强化所有 Skills 的匹配规则：预加载实验改善漏读，但用户要求按需加载；全局匹配实验收益不足，不进入交付。
- 自写 SVG 图表：重复维护轴、图例与 tooltip，已有 ECharts 可承担。
- 自动把过程组件移到最终答案：改变最终输出 Owner 并掩盖模型引导缺口。

## 后果

这是 Yuxi 的受限组件子集，完整 SDK 兼容、服务端动作、任意脚本、日期控件、饼图和持久表单状态不在范围内。图表最多60条、3个系列、高度180–400px；图片拒绝危险协议、凭据URL和宿主/沙盒路径。动作不承担审批或权限，也不表达业务完成。刷新或修改定义后表单恢复默认值，外链图片依赖源站。

自然选择和合法输出由模型决定，DeepSeek 的渐进发现存在漏读与非法草案。渲染成功不证明图片被识别或数据真实；预加载条件下的成功结果不能作为当前按需发现的成功率。新增专项测试脚本按用户要求移除，留存的阶段实验只能作为历史证据，常规 unit 不覆盖其全部协议边界。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 有限协议与草稿动作 | 模型JSON、DOM生命周期 | chatWidgets/MarkdownPreview/SessionWorkspace | 阶段parser、真实Vue DOM及正式会话检查 | 非法属性/动作拒绝，较早闭合消息生成期仍只读，草稿不自动提交 | Passed；专项脚本按要求移除，当前回归范围见下文 |
| 图表、图片和双主题 | 资源加载、主题、响应式 | WidgetChart/WidgetImage/WidgetRenderer | 正式消息SVG/表格、image decode、亮暗四宽度与刷新 | 图片401后授权恢复、资源释放、空/负数据；错误来源不计真实数据通过 | Passed，阶段实验与正式历史验证 |
| 默认按需发现 | 模型输入、Skill选择 | BaseContext/SkillsMiddleware/chat-widgets | 通用context/runtime unit与真实无预加载GLM实验 | DeepSeek漏读与非法JSON被拒绝 | Passed，GLM组件自然读取；DeepSeek稳定性不作保证 |
| 最终图表与真实来源绑定 | Turn/Run、工具来源 | 既有持久化链及Skill引导 | PostgreSQL回读自身工具结果/最终Message，独立来源复查与正式DOM | 过程有图但最终无图、搜索失败输出示例均被拒绝 | Passed，真实数据与历史绑定；模型触发条件见下节 |

### 真实模型与天气数据

隔离 Compose 使用真实 PostgreSQL、Redis、对象存储与sandbox，经过正常API、worker和公开会话；没有手工写消息、注入协议或拦截真实模型结果。凭据、原始响应、截图和私有探针仅在受限本地目录，不提交。

- GLM-5.3，skills=all、preload_skills=[]、tools=[]，自然请求不含Skill名/JSON或强制system_prompt：三类冷启动和同线程请求完成真实read_file与最终柱状图、图片卡片、推荐列表。Input/Turn/result Run/output Message一致；图表类别/数值逐项匹配输入、图片decode、推荐动作只追加草稿，数据库没有额外Input。两种主题及1440/1024/768/375px、刷新恢复通过。未读取图片时的错误内容推断只证明渲染，不计画面识别成功。
- DeepSeek-V4-Flash，无预加载实验：曾读旧HTML Skill、漏读组件或输出非法JSON；描述与跨行模板改善部分请求，仍不能承诺稳定。通用匹配规则实验收益不足。历史预加载实验九项正向和三项格式边界通过，但预加载方案已撤回，HTML边界已移除，均不证明当前渐进发现稳定性。
- 最终回复负向：真实运行已查询并在过程生成两图，最终只答已绘制；严格oracle以最终Run无两图拒绝。Skill补充最终输出要求后，真实读取说明和查询的会话最终包含两张七日折线图，模型值与该Turn自身工具结果对应，正式DOM与历史恢复通过。
- 真实天气原话“帮我生成未来7天北京和无锡的天气分布”：搜索配额耗尽后输出示例被来源oracle拒绝；后续真实Open-Meteo逐日查询，两城各2026-10-12至18日、最高/最低温28个值逐项匹配自身工具输出，开发者与Reviewer独立HTTPS复查一致。取数首轮文字有未验证归因/缺少来源，自然follow-up收敛为日期、单位、实际URL与两图；最新持久消息来源逐字匹配，双主题及刷新恢复通过。该实验使用当时预加载默认值，只证明取数、输出和渲染；当前无预加载DeepSeek原话未重新执行。
- 采样边界：另一来源仅三小时间隔，末日三个采样无法证明全天极值；真实follow-up纠正为采样最高/最低温。该结果不计完整逐日预报通过。独立oracle还拒绝重复类别与交换数值；恢复旧生成期绑定后DOM反例失败。

### 提交前检查

阶段已执行前端lint/unit/build与正式DOM；移除HTML后580项前端、2672项后端unit及历史天气双主题/刷新通过。默认预加载、清理分支和中间产物删除后的最终检查如下，测试数量减少来自显式删除的专项脚本与默认配置测试。

| 实际命令 | 结果 |
|---|---|
| frontend：`pnpm run lint:check`、`pnpm run test:unit`、`pnpm run build` | Passed，557 unit，build含strict typecheck |
| api：`PYTHONDONTWRITEBYTECODE=1 uv run --group test pytest test/unit -m 'not slow'` | Passed，2666 passed、60 skipped、7 subtests；使用隔离Compose的api service |
| api：context/discovery/Skill service/middleware/runtime相关unit | Passed，151 tests |
| `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts` | Passed，170 decisions、64 tests |
| docs：`node node_modules/vitepress/bin/vitepress.js build`、`git diff --check` | Passed，含相对链接检查 |
| 当前正式天气历史私有DOM探针与已有markdownPreviewLayout脚本 | Passed，两张七日图、亮暗四宽度/刷新，引用/复制/HTML源码；已删除演示路由无组件节点 |

当前无预加载DeepSeek自然请求未重新执行；旧预加载结果保留为历史事实。全新Reviewer覆盖完整staged diff、用户删除要求、当前文档和实际证据，独立打开正式天气DOM及截图核查轴标签、图例和两图，未发现阻断问题。
