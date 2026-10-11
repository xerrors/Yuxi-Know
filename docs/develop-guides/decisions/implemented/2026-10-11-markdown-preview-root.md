# Markdown 预览保留单根样式边界

状态：implemented
类型：bug-fix
Owner：frontend/src/modules/workspace/ui/MarkdownPreview.vue

## 问题

来源浮层作为第二个根节点加入 MarkdownPreview 后，Vue 不再把父组件的 scoped 标记传递给正文元素。会话文件预览的间距和字号规则失配，正文贴边；知识库片段的局部排版规则也依赖这一边界。手动转发 `$attrs` 只能传递 class、style 和事件，不能恢复 scoped 标记。

## 决策

### 实现方案

MarkdownPreview 恢复单个 DOM 根节点，继续承接调用方属性、事件与现有样式类。在根内新增专门由 Markdown 渲染器管理的正文容器，`previewRef` 指向该容器；来源浮层作为正文的同级子组件，并继续 Teleport 到 body。正文更新的 `replaceChildren` 不接触 Vue 拥有的浮层节点。文件预览与聊天等调用方继续拥有各自的间距，公共组件默认 padding 保持 0。

## 替代方案

- 在文件预览中使用 `:deep()`：能局部恢复 padding，但其他依赖公共组件根节点的 scoped 样式仍失效。
- 在公共组件添加默认 padding：导致聊天、Skills 与已有文档容器重复留白，且不能恢复其他失效的 scoped 样式。
- 将浮层直接放入原正文根节点：正文的 DOM 替换会删除 Vue 拥有的节点和锚点，破坏浮层更新。

## 后果

正文增加一层容器，调用方仍在原有根节点上控制布局。事件继续冒泡，来源浮层的 Teleport 与父组件 scoped 样式互不影响。没有持久化、权限、API 或依赖变更。

## 验证

- `docker compose exec -T frontend node --test test/unit/markdownPreviewScope.test.js`：Passed，真实 Vue 编译与渲染验证父 scope、class 与 style。用 HEAD 的旧组件源码作为读取结果执行同一测试，因缺少 `data-v-caller` 断言失败；不修改工作树。
- `playwright-cli -s=md-padding run-code --filename=frontend/test/browser/markdownPreviewLayout.js`：Passed，真实组件在浏览器中挂载，回读 DOM、计算样式与标题位置。修复前同一脚本因缺少父 scope 失败；修复后上下 padding 16px，桌面左右 14px、375px 宽度左右 10px，字号 13.6px。验证浅色/深色下 1440、1024、768、375px 宽度、全屏、紧凑正文、文档容器与知识库片段局部排版，以及来源分页、正文更新、键盘焦点、原文高亮、代码复制和 HTML iframe 身份保留。浏览器截图保存于本地临时目录，不入库。
- `docker compose exec -T frontend pnpm run lint:check`、`docker compose exec -T frontend pnpm run test:unit`、`docker compose exec -T frontend pnpm run build`：Passed，全量 unit 559 项；build 保留现有大 chunk 提示。
- `python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`：Passed，契约测试 64 项。
- `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow'`：Passed，2670 passed、55 skipped、7 subtests passed；skip 不计为通过。
- `cd docs && pnpm run build`：通过，保留完整相对链接检查；修正测试审计文档中的两处根目录 AGENTS 链接为公开源码链接。
- 浏览器使用合成内容挂载真实组件，不读取业务文件；没有对用户截图中的原始文档执行端到端业务操作。
