# 前端纯逻辑测试从源码断言迁移

状态：implemented
类型：testing
Owner：frontend/src/modules/knowledge/model/uploadMetadata.js

## 问题

前端 unit 中有一批测试通过 `readFileSync` 读取 SFC/JS 源码，再用正则或 `compileScript` 断言实现细节。审计指出这类测试会在行为损坏时通过、在无害重构时失败，并特别点名 `file_upload_folder.test.js`。迁移前有 52 个 unit 文件使用 `readFileSync`/`readFile` 读取源码；本批后为 49 个，其中一部分是资产/构建产物检查，另一部分确实是实现细节断言。

## 决策

### 实现方案

先迁移四处可以安全提取纯逻辑的用例：

- `agents/model/agentOrder.js` 拥有管理列表的搜索与创建时间排序；`AgentManagePanel.vue` 只调用该函数。
- `settings/model/cooperationDepth.js` 拥有协作深度“完整非负整数”校验；`BasicSettingsSection.vue` 只负责把合法值写入配置。
- `knowledge/model/uploadMetadata.js` 拥有上传完成文件的路径、哈希、大小、相对来源路径汇总，以及隐藏文件/隐藏目录判断、上传准入和 `source_paths` 参数组装；`FileUploadModal.vue` 复用这些函数。
- `session/model/artifactPresentation.js` 拥有交付物倒序文件项和折叠可见项；`AgentArtifactsCard.vue` 只负责渲染与交互。

对应测试改为直接调用模型函数，移除 `compileScript`、源码切片和正则断言。`file_upload_folder.test.js` 仍保留一条上传文件夹菜单的源码装配检查；该行为最终应由 browser 覆盖，元数据与隐藏文件逻辑已不再读源码。

剩余 49 个读源码文件按风险继续处理：`workspaceOpenFile` 等仍用 `compileScript` 行为 harness 的用例优先提取 composable/model；`toolRegistry` 等仍用 `readFileSync` + 正则的接线守卫转成 ESLint/AST 规则；CSS/ARIA/SFC 接线检查交给 browser；资产字节检查保留。不得把新的行为断言写回源码正则。

## 替代方案

- 删除这些测试：会丢失现有覆盖，且无法区分真实回归和无害重构，不采用。
- 保留 `compileScript` 执行 setup：能测行为，但仍与 SFC 结构和导入顺序耦合；纯逻辑提取更直接，不采用。
- 全部迁移到浏览器测试：纯排序、校验和元数据汇总不需要浏览器，成本过高，不采用。

## 后果

四处逻辑的行为变化现在由模型测试直接失败，不再依赖源码文本。组件仍保留原有的输入、提示和提交边界，只是把纯计算移出 setup。剩余源码断言仍是技术债，下一批优先处理 `workspaceOpenFile` 等仍用 `compileScript` 的用例，并把 `toolRegistry` 等正则接线守卫转成 ESLint/AST 规则。

## 验证

旧能力不存在：`agentManageOrder.test.js`、`cooperationSettings.test.js` 与 `artifactPresentation.test.js` 不再读取 SFC；`file_upload_folder.test.js` 的元数据断言不再正则匹配源文件。

重新引入条件：只有当逻辑确实依赖 Vue setup 生命周期、无法提取为纯函数时，才保留组件级行为测试；不得回归为源码文本断言。

- `pnpm run test:unit`：779 passed。
- `pnpm run lint:check`：通过。
- `pnpm run build`：通过；主入口 1,253.02 kB。
- 新模型文件与迁移测试的 Prettier 检查：通过。
- `artifactPresentation.test.js`、`agentManageOrder.test.js`、`cooperationSettings.test.js`、`file_upload_folder.test.js`：全部通过。
- 读源码 unit 文件：52 → 49（`agentManageOrder`、`cooperationSettings`、`artifactPresentation` 完全移除；`file_upload_folder` 保留 1 条 UI 装配检查）。
- 未执行浏览器 E2E；本次只提取纯计算，组件模板与交互未改变。
