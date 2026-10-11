# Web 显示层品牌与标签页标题

状态：implemented
类型：feature
Owner：web/src/stores/info.js

## 问题

浏览器标签页标题由 `web/index.html` 硬编码，不随运行时品牌配置更新：部署方把站点信息改为自有品牌后，标签页仍长期显示源码默认品牌，与页面内品牌不一致。站点信息配置 `backend/package/yuxi/config/static/info.template.yaml` 是运行时品牌的语义 Owner，但标签页是同一字符串的第二个独立 Owner，两者会各自漂移。

## 决策

标签页标题由运行时品牌配置驱动，静态 `web/index.html` 只保留与默认品牌一致的初始值；`organization.name` 是标题的品牌来源，缺少时回退到源码默认品牌 `睿狐`，后缀 `- Knowledge Management` 作为页面用途描述保留在代码中。站点信息模板的三个品牌字符串同步更新为 `睿狐` / `Smartfox`，登录页与工作台品牌回退字面量一并更新。

### 实现方案

`web/src/stores/info.js` 的 `setInfoConfig` 是所有品牌配置写入的汇合点（初次加载、`HomeView` 重试、`AppLayout` 加载、`DebugComponent` 强制刷新都经它），在此写入 `document.title`；`typeof document !== 'undefined'` 守卫与同文件 `localStorage` 读取一致，使 SSR 单测无需 DOM。读取失败路径不调用 `setInfoConfig`，标签页保持 `web/index.html` 的静态默认值，因此失败时仍显示正确品牌。

`backend/package/yuxi/config/static/info.template.yaml` 拥有站点信息默认值：`organization.name`、`branding.name`、`footer.copyright` 三项同时替换，避免登录页 `LoginView` 的“组织名 + 品牌名”并排渲染出现混品牌。`web/src/views/LoginView.vue` 与 `web/src/layouts/AppLayout.vue` 的品牌回退字面量属于同一显示面，同步更新。

## 替代方案

让 `index.html` 继续硬编码品牌并只在构建期替换，会保留两个品牌 Owner 与漂移可能；改为读取 `branding.name` 更贴合“产品名”语义，但会使标签页显示英文品牌并与页面内中文品牌不一致；新增 `branding.document_title` 配置字段会引入没有其他 consumer 的长期维护表面。

## 后果

部署方修改站点信息后，标签页与页面内品牌一致；标签页品牌来自 `organization.name`，而该字段声明为“完整组织名称”，部署方若把公司全称写入该字段，标签页会显示公司全称——这是接受的取舍，记录于此供未来重开。聊天机器人人设、CLI 本地 UI、文档站、wire 契约与 GitHub 仓库地址不在本次范围。

## 验证

- Passed：`docker compose exec -T web pnpm run test:unit`（396 passed；新增两例：配置写入标签页标题且组织名缺失时回退、读取失败不覆盖静态标题）。
- Passed：`docker compose exec -T web pnpm run lint:check`、`docker compose exec -T web pnpm run build`；构建产物 `dist/index.html` 标题为 `睿狐 - Knowledge Management`，`grep -c "语析 - Knowledge Management"` 为 0。
- Passed：`python3 scripts/verify_engineering_contracts.py`（47 decisions / 182 docs / 250 web sources）。
- 未验证：未做真实浏览器页面验证（标签页由静态标题切到运行时标题的过渡未截图）；未运行 backend integration / E2E。

旧能力不存在：`web/index.html` 与站点信息模板中面向用户可见的 `语析` 字符串已清除；标签页不再由静态文件独占品牌。

重新引入条件：任何让标签页品牌脱离 `organization.name` 或重新硬编码到 `web/index.html` 的变更，必须引用本记录、说明部署方影响，并给出兼容窗口或回退方案。
