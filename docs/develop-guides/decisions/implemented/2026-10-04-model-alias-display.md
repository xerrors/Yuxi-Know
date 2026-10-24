# 前端按模型目录别名展示模型名称

状态：implemented
类型：bug-fix
Owner：web/src/composables/useModelDirectory.js

## 问题

模型配置支持为已启用模型设置展示别名（`display_name`），模型选择器的下拉目录已展示别名，但选中态触发器与消息底部引用栏仍展示供应商原始模型名：前者从 `model_spec` 截取，后者直接读取 `response_metadata.model_name`。别名设置无法在用户实际看到模型名的地方生效。

## 决策

### 实现方案

新增共享 composable `web/src/composables/useModelDirectory.js`：按 `modelType` 维护模块级单飞缓存（加载 `modelProviderApi.getV2Models` 目录），暴露 `load`、`resolveDisplayName({spec | modelId})` 与 `invalidateModelDirectory`；解析先按完整 `spec` 精确匹配目录项，再退化为唯一 `model_id` 匹配，跨供应商存在多个同 `model_id` 时返回空串不解析。`load` 带失效纪元守卫：`invalidateModelDirectory` 递增 epoch，失效前发起的在途旧响应不回写共享缓存，改为重新等待新一代结果。展示接入两处：`ModelSelectorComponent.vue` 在挂载与 `model_spec` 变化时解析别名用于选中态文本，标题取别名或完整 spec；目录加载期间 `model_spec` 已切换时放弃本次结果、由 watch 重新触发；刷新模型缓存时先失效目录再重新解析，未命中回退原 `full/short/mini` 规则。`RefsComponent.vue` 按 `response_metadata.model_name` 解析唯一别名，同样在原始名变化时放弃过期结果；目录未就绪、歧义或请求失败时回退原始名称。无后端接口、持久化或协议变更。

### 口径

别名只在展示层解析，事实源始终是后端模型目录的 `display_name`；`model_id` 有歧义（跨供应商同名）时宁可不解析也不猜，保留原始名称。

## 替代方案

后端在 `response_metadata` 直接写入别名可避免前端目录请求，但会在仅用于展示的位置改变模型响应协议，并把别名快照固化进历史消息，模型改名后旧消息不更新。每个引用栏组件各自请求目录会产生按消息数量的重复请求，因此改为模块级共享缓存。

## 后果

模型别名的展示 Owner 收敛到模型配置目录投影，前端不再从 spec 推断展示名。目录仅在会话首次需要时请求一次并全应用复用，别名变更需通过模型选择器的刷新动作或页面重载生效。消息引用的别名按 `model_id` 唯一匹配，存在同名模型时保留原始名称。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 选中态与引用栏按目录别名展示，未命中/歧义/失败回退原始名称 | 展示继续从 spec/`response_metadata` 推断供应商原始名 | `useModelDirectory.resolveDisplayName` 与两个组件接入 | `web/test/unit/modelDirectory.test.js`（spec/唯一 model_id/歧义不解析）；`modelSelectorAlias.test.js`（命中显示别名、未命中回退截取名且标题保持完整 spec、请求失败回退）；`refsModelAlias.test.js`（唯一命中、跨供应商同名保留原始名、请求失败回退）；`docker compose exec web pnpm run test:unit` → 406 passed / 0 failed | `modelSelectorAlias.test.js` 与 `refsModelAlias.test.js` 的失败用例在实现改为"首个匹配即用"或去掉回退分支时失败；`modelDirectory.test.js` 同名歧义断言在退化为猜测匹配时失败 | Passed |
| 失效后乱序完成的在途旧响应不污染共享目录；选择器在加载期间切换 spec 不回写过期别名 | epoch 缺失时旧响应覆盖新缓存；spec 切换后旧结果覆盖新展示 | `useModelDirectory.load` epoch 守卫与 `ModelSelectorComponent.syncResolvedModelAlias` 捕获序检查 | `modelDirectory.test.js`「失效后乱序完成的在途旧响应不回写共享目录」；`modelSelectorAlias.test.js`「慢目录返回期间切换 spec 时不回写过期别名」 | 临时移除 `load` 的 epoch 守卫后乱序用例失败于 `旧别名 !== 新别名`；移除选择器捕获序检查后切换用例失败于过期别名回写；恢复后均通过 | Passed |
| 目录共享缓存不产生按消息数重复请求 | 每个引用栏各自拉取目录 | `useModelDirectory` 模块级单飞缓存 | `modelDirectory.test.js` 失效后重载重新请求断言（单飞与重取次数可观察）；`modelSelectorLoading.test.js` 覆盖加载、失败重试与类型隔离 | 移除缓存后重新请求断言得到多倍调用次数 | Passed |
| 构建与 lint 不回归 | 前端编译/lint gate | `web` 构建链 | `docker compose exec web pnpm run build` 通过；`npx eslint` 对全部改动与新增文件无输出 | 不适用 | Passed |

未验证范围：浏览器内真实页面的最终视觉表现（浅/深色与响应式）`Not run`；`RefsComponent` 的"加载期间原始名变化放弃过期结果"守卫与选择器同型，但因 SSR 单次渲染无法在单实例内切换 props，组件级负向用例 `Not run`（composable 层 epoch 与选择器层已覆盖同型缺陷）；`response_metadata.model_name` 与目录 `model_id` 的一致性依赖后端当前投影（`models/chat.py`），无契约测试，后端投影变更时引用栏将静默回退原始名称；目录接口持续失败时各组件挂载会各自重试（无退避），属已知取舍。别名命中依赖后端目录已配置 `display_name`，配置入口行为不在本记录范围。
