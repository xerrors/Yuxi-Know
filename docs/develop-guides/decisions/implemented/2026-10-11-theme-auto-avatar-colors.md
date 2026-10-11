# 自动主题与头像色卡一致性

状态：implemented
类型：feature
Owner：frontend/src/shared/model/theme.js

## 问题

用户需要在浅色、深色、跟随浏览器之间连续切换，同时保持头像的主体配色。二态主题与点击即关闭的菜单无法完成这个操作；夜间统一套用另一组颜色会让官方原色的不同风格与同一身份明显变色。

## 决策

### 实现方案

[主题 Store](https://github.com/xerrors/Yuxi/blob/main/frontend/src/shared/model/theme.js) 拥有 light、dark、auto 选择，继续以 localStorage 的 theme 键保存。auto 使用浏览器 prefers-color-scheme 并实时更新；isDark 提供解析后的实际明暗状态，根节点与 Ant Design 控件同步更新。默认保持浅色，既有布尔 setTheme 调用继续可用。

[用户菜单](https://github.com/xerrors/Yuxi/blob/main/frontend/src/modules/settings/ui/UserInfoComponent.vue) 拥有浮层开关，主题操作保持展开，其他操作与点击外部关闭。菜单与 Dashboard 主题入口显示当前模式并按 light → dark → auto → light 轮换。

[头像色卡](https://github.com/xerrors/Yuxi/blob/main/frontend/src/shared/lib/avatar/presets.js) 拥有配色：命名色卡明暗共用主体颜色，夜间底纸和墨色独立；官方原色保留上游原生主体与对比色，仅对 Glyphs、Clay 切换底纸。Shape Grid 保留彩色背景与原生对比形状。设计约定由[设计规范](../../design.md)解释。

## 替代方案

三项子菜单增加操作步骤，与连续点击轮换不符。默认切为 auto 会改变未选择主题用户的现有外观，因此保持浅色默认。仅调小夜间主体色差仍会让官方原色的不同风格共用错误色板，因此保留各自原作。

## 后果

自动模式持久保存选择，不保存当前解析结果。头像形状、身份 seed、许可和自定义图片优先级保持现有契约；Shape Grid 与 Gaze 的官方原色在明暗模式输出相同。

## 验证

主题与头像相关 unit 6 项通过。主题 unit 覆盖三态轮换、初始化、保存选择、实时媒体偏好响应与显式明暗覆盖；头像 unit 对照固定版本的上游原生色板与实际 SVG，验证四种风格、四套预设、多个身份的主体填色。旧实现使主题三态与色卡一致性断言失败。临时恢复未受控 Dropdown，使真实菜单探针在主题轮换后以“主题点击后菜单收起”失败；恢复修复后探针通过。

真实 Vite 页面执行 `frontend/test/browser/themeModes.js`，核对连续菜单点击、外部与设置关闭、三态刷新、浏览器偏好实时变化、显式覆盖、Dashboard 轮换和 375px 窄屏。执行 `frontend/test/browser/avatarThemeColors.js`，回读 16 组、32 张实际解码图片的 SVG 主体填色，验证无失败占位。截图只保存测试头像和菜单操作区，排除账户数据。

`docker compose exec -T frontend pnpm run lint:check`、`pnpm run test:unit`（562 项）、`pnpm run build` 通过；`python3 scripts/verify_engineering_contracts.py`、`python3 -m unittest scripts.test_verify_engineering_contracts`（64 项）、`docker compose exec -T api uv run --group test pytest test/unit -m "not slow"`（2667 passed，60 skipped）通过。文档 `pnpm run build` 与补丁检查通过。浏览器验证使用 Chromium；Firefox、WebKit 未执行。
