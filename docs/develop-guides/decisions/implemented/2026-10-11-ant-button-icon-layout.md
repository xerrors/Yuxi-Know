# Ant Design 按钮统一图标布局

状态：implemented
类型：bug-fix
Owner：frontend/src/assets/css/antd.less

## 问题

Ant Design Vue 4 的按钮间距选择器识别 `.anticon`，Lucide 的 SVG 使用 `.lucide`。未添加局部 flex 样式的按钮缺少图文间距，现有按钮又分别使用 gap 与 Ant 原生 margin，无法统一对齐。

## 决策

### 实现方案

共享 `antd.less` 为 `button.ant-btn` 与 `a.ant-btn` 提供居中 flex 布局及 8px 图文间距，清除 Ant 图标与文字之间、加载图标内部的重复 margin。图标不收缩，保留调用方指定的尺寸。主入口继续导入共享样式，按钮的 props、slots、事件、禁用和加载机制由 Ant Design 拥有。

`main.css` 删除重复的 Ant 按钮图标适配规则，保留原生按钮使用的 `lucide-icon-btn`。业务按钮复用共享居中与 gap，局部样式只维护业务布局。设计规范明确 Ant 按钮使用 `#icon`，纯图标按钮提供可访问名称。

## 替代方案

- 每个按钮添加样式类：依赖调用方记忆，容易再次遗漏。
- 包装并替换全部 `a-button`：为纯布局问题增加 props、slots、事件与 ref 的透传维护。
- 给 Lucide 增加 `.anticon`：混用图标库标识，既有 flex 按钮仍可能叠加原生 margin。

## 后果

统一规则覆盖所有 Ant 按钮，业务内容布局和显式尺寸继续由调用方拥有。Ant Design 的 props、状态和行为保持原实现，业务组件直接使用图标插槽。此变更不涉及反馈存储、权限或后端。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| Lucide、Ant 原生与加载图标同文字居中并保持单份间距 | 真实 DOM 和计算样式 | antd.less | 5173 页面及真实 Button 渲染矩阵 | 浏览器将共享 gap 覆盖为 0 时，加载状态间距断言失败 | Passed |
| 链接、纯图标、尺寸、禁用和加载行为保持可用 | 真实控件 | Ant Button 与共享样式 | 浏览器矩阵、lint、unit、build | 加载期间点击不触发事件；纯图标按钮不增加空白间距 | Passed |

`frontend/test/browser/antButtonIcons.js` 在真实 5173 页面挂载实际 Vue 与 Ant Button，在浅色与深色模式覆盖 12 种组合：三档尺寸、默认/主/文本按钮、链接、禁用、纯图标、既有样式类、纯文字、行内尾部图标及 Ant 原生图标。DOM 测量确认图文间距为 8px，中心偏差小于 1px；加载图标无额外 margin，禁用与加载期间不触发事件，普通点击有效，加载结束后宽度恢复。共享 gap 以明确的浏览器 CSS 覆盖为 0 后，相同 oracle 因加载状态实际间距为 0 失败；恢复后通过。实际反馈刷新按钮另行测得间距 8px、垂直中心偏差 0px。

执行结果：前端 `lint:check`、559 项单测与 `build` 通过；工程信任检查与 64 项验证器单测通过；文档构建与 `git diff --check` 通过。浏览器矩阵挂载的组件和事件计数仅存在于当前页面，结束时卸载，不创建业务数据。
