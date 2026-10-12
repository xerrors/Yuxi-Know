# 移除对话内 HTML Preview

状态：implemented
类型：simplification
Owner：frontend/src/shared/lib/markdown_preview.js

## 问题

用户要求移除 HTML Preview。对话可视化由有限widget承担，旧Skill、Markdown围栏与iframe执行/高度同步构成另一条生成和渲染路径。用户明确将重建环境，旧安装状态不需要应用内迁移。

## 决策

### 实现方案

删除内置html-preview Skill、HTML围栏renderer、MarkdownPreview的iframe高度消息及样式。旧html:preview围栏按普通代码块显示；SVG、引用定位和widget继续由各自Owner拥有。节点复用只保留widget，使用方法见[组件决定](2026-10-12-chat-widgets.md)。

内置同步沿原实现只发布当前Skill定义，不查询、删除或撤下旧html-preview索引/投影。运行环境重建后同步当前目录；本变更不包含旧数据库/文件迁移。独立HTML文件交付物属于文件预览链路，入口保留。中间演示页、示例数据和新增专项测试脚本一并移除。

## 替代方案

- 仅删除Skill：历史围栏仍执行iframe，未满足移除渲染要求。
- 保留兼容renderer：留下用户要求删除的维护路径。
- 启动时清理旧索引/投影：用户将重建环境，不承担这个兼容consumer，删除特殊分支与迁移测试。
- 删除独立HTML文件预览：扩大到研究交付物，超出当前对话预览消费者范围。

## 后果

历史HTML围栏显示源码是公开行为变化。旧环境中的数据库、安装副本和用户投影不会由启动自动清理，环境重建是本次交付前提。此变更不删除用户文件或自定义Skill。

## 验证

旧能力不存在：当前builtin发布目录无html-preview，Markdown没有HTML预览parser、iframe创建、高度同步或对应导出；旧完整、未闭合和嵌套围栏按代码显示。Widgets演示路由、示例文件和新增专项脚本不存在，正式renderer与按需Skill保留。

重新引入条件：有明确当前消费者、独立协议/权限边界及真实数据与浏览器验证，再提案。

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 旧围栏显示代码 | Markdown、DOM | markdown_preview/MarkdownPreview | 阶段3个unit与12种真实DOM案例；当前已有layout脚本 | 完整/流式未闭合/嵌套/旧内部标记均无iframe | Passed，阶段专项脚本按用户要求移除 |
| 当前发布不含旧能力，无清理特例 | shipping、启动 | builtin discovery/shared.py | 目录发现unit、源码diff与符号搜索 | 当前发布缺少旧Skill；同步代码恢复原实现 | Inspected，最终unit结果见组件决定 |
| widget与引用仍可用 | Vue生命周期、主题、引用 | MarkdownPreview/SessionWorkspace | 阶段草稿、引用/复制与正式天气DOM | 值/节点丢失或历史两图缺失失败 | Passed，当前回归结果见组件决定 |

删除前的真实PostgreSQL旧安装清理测试曾通过，但该分支与专项测试均已删除，不作为当前能力证据。阶段HTTP目录与文件回读无旧builtin只说明该已清理环境，不能证明现有代码迁移旧安装。

当前常规gate、正式天气双主题和刷新验证与独立Review结果由[组件决定](2026-10-12-chat-widgets.md#提交前检查)维护。已有turnReferenceBoundaries脚本已适配旧围栏源码行为，其历史专用fixture未在隔离环境重建；引用交互由已有markdownPreviewLayout真实DOM验证。
