# Skill 导入缺 slug 时从展示名派生

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/services/skills/package.py

## 问题

Issue #1073：上传仅含中文等展示名、未声明 `slug` 的 Skill ZIP 时，后端把 `name` 当作 slug 校验并返回 400；前端将普通字符串 detail 脱敏为「请求参数错误」，用户看不到真实原因。

## 决策

### 实现方案

`parse_skill_markdown` 在缺少 `slug` 时：若 `name` 本身符合 slug 规则则沿用；否则用已有 `pypinyin` 从展示名派生稳定 slug，失败再哈希兜底。`rewrite_frontmatter_slug` 始终写入 `slug` 字段，仅当 `name` 曾充当 slug 身份时同步改写 `name`，保留中文等展示名。Skill 路由的 ValueError 以 `{code, message}` 业务 detail 返回；前端 Skill 相关 UI 通过 `resolveApiErrorMessage` 展示 `message`。

## 替代方案

强制用户在 ZIP 中补 `slug`：不兼容常见第三方 Skill 包。前端放宽任意字符串 detail 透传：破坏现有脱敏契约。引入独立 slug 配置或兼容层：当前无第二 consumer。

## 后果

无 `slug` 的展示名包可导入；显式非法 `slug` 仍失败。冲突重写后安装快照会持久化 `slug` 字段。Skill API 错误 shape 从纯字符串变为业务对象，依赖字符串 detail 的客户端需读 `message`。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 中文展示名无 slug 可派生并安装 | 仍把 name 当 slug 校验 | package.py | unit：`test_parse_skill_markdown_derives_slug_from_chinese_display_name`、`test_skill_zip_import_derives_slug_from_display_name_not_zip_filename`；`docker compose exec -T -u root api uv run --group test pytest test/unit/services/skills/test_skill_service.py -k "parse_skill_markdown or zip_import or rewrites_conflicting" -q` → 12 passed | 显式非法 slug：`test_skill_zip_import_rejects_invalid_explicit_slug` | Passed |
| 冲突重写保留展示名 | rewrite 覆盖 name | package.py | 既有 `test_skill_zip_import_rewrites_conflicting_slug_not_display_name` | name 曾为 slug 时仍改写（`test_skill_upload_prepare_confirm_rewrites_conflicting_name`） | Passed |
| 前端展示后端 message | 仍只显示「请求参数错误」 | base.js + Skill UI | `docker compose exec -T web npm run test:unit` 中 `业务错误 detail 透传 code/message 且 resolveApiErrorMessage 可读` 通过；Skill 组件改用 `resolveApiErrorMessage` | 缺 code/message 的 400 仍脱敏（既有 api_boundary） | Passed |
