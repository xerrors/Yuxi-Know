# 首页任务链展示改为滚动驱动

状态：implemented
类型：feature
Owner：docs/.vitepress/theme/components/YuxiHome.vue

## 问题

官网首页「从检索到交付，沿一条任务链发生」段落用左侧 tablist 控制右侧单张截图，读者必须逐次点击才能看到四个产品界面；顺着页面往下滚时，左侧高亮与右侧画面都不前进。期望的行为是左侧保持不动、右侧画面依次上移，当前步骤随阅读位置自然高亮。

## 决策

桌面端把左侧步骤列固定在导航栏下方，右侧改为四个截图面板纵向排列；面板进入视口中部判定带时把对应步骤设为当前项，当前步骤离开判定带后由带内相邻面板接管，点击步骤则把该面板平滑滚到视口中央。窄屏不再固定左侧，步骤改为两列概览加面板顺序排列。

### 实现方案

`YuxiHome.vue` 拥有该段落的交互与样式，`productScenes` 仍是唯一数据源。模板为每个场景渲染一个步骤按钮（`#yx-step-<key>`）和一个面板 `figure`（`#yx-panel-<key>`，`:data-scene-index` 提供序号），面板标题由 `figcaption` 呈现。

- 状态：`activeScene` 是唯一的当前步骤索引，默认 0；`scenePanels` 保存函数 ref 收集到的面板元素，`sceneVisible` 记录当前落在判定带内的面板索引，`sceneObserver` 持有观察器。
- 滚动：`observeScenePanels()` 在 `onMounted` 建立 `IntersectionObserver`，`rootMargin: -42% 0px -42% 0px` 把视口收成中部 42%–58% 的判定带。面板进入判定带时接管 `activeScene`；当前步骤离开判定带后由带内索引最小者接管，否则两块面板同时在带内（725px 高视口下约 53px，随视口高度增大）时，高亮会滞留在已经离开判定带的那一块。`onBeforeUnmount` 断开观察器。`activeScene` 只由观察器写入。
- 点击：`scrollToScene(index)` 只用 `scrollIntoView({ block: 'center' })` 把面板滚到视口中央，不直接改写 `activeScene`；`prefers-reduced-motion` 命中时改用 `auto`，不做平滑动画。
- 样式：`.yx-tour__steps` 桌面端 `position: sticky`，顶距 `calc(var(--vp-nav-height, 64px) + 40px)`；`.yx-screen` 高度 `min(76vh, 660px)`，非当前面板 `opacity: .55` 与 `scale(.98)`，当前面板恢复原状；≤900px 取消固定、面板恢复原尺寸并取消弱化。面板标题按外框内边距缩进，与截图左边对齐；视口高度 ≤660px 时步骤内边距与间距收紧为 8px/4px；深色模式下 `.yx-screen__backdrop` 描边改用 `--yx-line`。
- 语义：段落不再声明 `tablist`/`tab`/`tabpanel`，四个步骤与四个面板同时可见，步骤按钮用 `aria-current="step"` 标注当前项，按钮逐个可 Tab 聚焦，不再使用 roving tabindex 与方向键处理。面板是 `figure`，标题由可见的 `figcaption` 呈现，figure 不设可访问名：指向步骤按钮的 `aria-labelledby` 会把按钮里的描述文案带成面板名，与图上可见文字不一致。本决定取代[首页品牌刷新](../archived/0.7.3/01-engineering-trust-and-docs/2026-09-04-docs-home-brand-refresh.md)中产品截图的水平 tablist 约定与 `aria-selected` 验证项。
- 失败边界：段落依赖 `IntersectionObserver`，同组件的 `v-reveal` 也依赖它，不可用时不做兼容分支；图片沿用原生 `loading="lazy"`。

这是复用现有 `v-reveal` 与既有视觉语言的局部交互改造，没有新增依赖、持久状态或配置项，也没有待裁决的架构方案，直接记录为 implemented。

## 替代方案

- 保留单张截图，把段落拉长并按滚动进度换图：右侧画面不真正上移，与「面板往上滚」的期望不符，也丢掉面板本身在移动的视觉线索。
- 用 `scroll` 事件逐帧计算进度：需要节流并自行处理边界，`IntersectionObserver` 已经能表达「进入判定带才接管」。
- 保留 tablist 语义、只把点击换成滚动：四个面板同时可见后与「同一时刻只有一个 tabpanel」矛盾，会误导辅助技术。
- 点击时直接改写 `activeScene`：平滑滚动途中掠过的面板会把高亮拉回去，实测出现「跳到目标 → 回跳到中间项 → 再回到目标」，因此改为只由滚动位置决定。

## 后果

- 四个截图同时进入 DOM，是否加载交给原生懒加载按视口决定；段落高度约四屏，滚动路径变长。
- 桌面端左侧固定，读者在任何位置都能看到当前步骤；≤900px 改为步骤概览加顺序面板，不做固定。
- 旧的 `yx-tabs`、`yx-tab`、`yx-screen-swap` 类与方向键处理不再存在，没有保留兼容分支。
- 键盘用户不再用方向键切换步骤，改为 Tab 逐项聚焦、Enter 定位。
- 点击相隔较远的步骤时，平滑滚动途中掠过的面板会依次点亮，高亮表现为顺读推进而不是直接跳到目标。
- 桌面端视口高度 ≥555px 时，四个步骤在 901–1450px 各档宽度下都完整留在视口内；≤900px 取消固定后本来就不受视口高度限制。更矮的视口仍有裁切：1450×540 不裁，1024×540 与 901×540 各裁 14.3px（折行宽度下步骤列更高）。高于 660px 的视口保持 18px 内边距与 8px 间距，步骤列在 ≥1200px 宽时高 500.5px。

## 验证

- `cd docs && pnpm run build`：通过，无死链与构建错误；`python3 scripts/verify_engineering_contracts.py` 通过（218 decisions），`python3 -m unittest scripts.test_verify_engineering_contracts` 通过（66 tests），`git diff --check` 干净。
- 真实浏览器（VitePress dev，视口 725px 高）：`.yx-tour__steps` 计算样式为 `position: sticky`、`top: 104px`，该列顶部在 scrollY 2202–3702 之间恒为 104px。
- 用真实滚轮事件从段落上方连续下滚：当前步骤按 0→1→2→3 单调推进；真实鼠标点击第四个步骤同样为 0→1→2→3，面板中心与视口中心偏差 2px 内。
- 判定带回读：`entry.rootBounds` 为视口高度 725px 的 42%–58%，即 page y 305–421。
- 高亮滞留修复：下滚到 y=2260（两块面板同时在判定带内，当前步骤 1）后向上滚 240px，当前步骤回到 0；一次性从 2260 跳到 2020 同样回到 0。
- 点击相邻上方步骤：在 y=2260 点击第一个步骤，面板 0 居中后当前步骤为 0，四个面板 `opacity` 为 `1 / .55 / .55 / .55`，`aria-current` 与明暗一致。
- 切换点稳定性：在判定带同时容纳两块面板的滞后区间内取 y=2250、2260、2270、2280、2290、2296 六个落点，每处静置 8s 采样 32 次，当前步骤都是单一值，浏览器侧只记录到定位瞬间的 enter 批次，滞后区间内没有翻转。
- 语义抽查：`role="tablist"/"tab"/"tabpanel"` 数量为 0，步骤按钮逐个可 Tab 且 `:focus-visible` 有 3px 轮廓；`Accessibility.getPartialAXTree` 回读 `.yx-screen` 为 `role=figure`、名称为空（标题以 `figcaption` 内容呈现）。
- CDP 模拟 `prefers-reduced-motion: reduce`：点击后滚动瞬时完成（scrollY 1602 → 3775）且当前步骤跟随为 3，合成点击与真实鼠标点击结果一致。
- CDP 模拟 1280/1024/900/820/680/390 六档宽度：>900px 为固定单列步骤，≤900px 转 `static` 两列，≤680px 单列并隐藏步骤描述；各档横向溢出为 0。
- 面板标题与截图对齐：`figcaption` 文本左边与截图左边在 1440、820、390 三档宽度下相差 1px（外框描边），此前分别偏左 35、26、19px。
- 深色模式面板描边：`html.dark` 下外框描边取 `--yx-line`（`rgb(61, 67, 63)`），按 WCAG 相对亮度与面板底（`color-mix(in srgb, var(--yx-paper) 90%, var(--yx-amber))`）的对比度为 1.44，与纸张底为 1.75；此前的 14% 描边与面板底为 1.00。浅色模式描边仍为 `rgba(39, 44, 42, .14)`，对比度 1.30，未变。
- 矮视口步骤列（等 scrollY 连续三次读数一致、步骤列吸顶 top 为 104 后取值）：1450×560、1450×540 与 1024×560 吸顶后列底都在视口内，第四个步骤完整可见；1024×540 与 901×540 列高 450.3px、列底 554.3px，各裁 14.3px。收紧前 1450×560 列高 500.5px、列底 604.5px，第四步被裁 44.5px。
- 样式调整后重跑行为回归：真实滚轮从段落上方下滚的当前步骤为 0→1→2→3 单调推进；y=2260 向上滚 240px 回到 0；725px 高视口下判定带与滞后区间行为不变。
- 未验证：Safari 与 Firefox 下的 `overflow: clip` 与 `sticky` 组合、真机触摸滚动、构建产物下的交互（本机只有 Chromium 与 dev server）。
