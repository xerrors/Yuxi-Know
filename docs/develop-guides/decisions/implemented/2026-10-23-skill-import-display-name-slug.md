# Skill 展示名导入与业务错误展示

状态：implemented
类型：bug-fix
Owner：backend/yuxi/modules/extensions/skills/package.py

## 问题

缺少 `slug` 的外部 Skill 包使用中文或带空格的 `name` 时，上传被机器标识校验拒绝。Skill 路由的字符串错误与前端业务错误契约不匹配，用户只能看到笼统提示。

## 决策

### 实现方案

包解析器保留展示名；显式 slug 严格校验，缺少 slug 时优先沿用合法 name，否则使用已有拼音依赖、小写和短横线派生稳定标识，无法得到合法字符时使用名称哈希。复制安装内容时写入展示名派生的 slug，只有实际标识改变才改写旧式 name-only 包；同名冲突仍由共享安装服务分配后缀。显式 slug 或旧式 name 标识未改变时保留原文件字节和修订，编辑其他文件也保持根文件不变。

YAML 解析失败只返回语法提示，远程 CLI 失败只返回通用提示，复制错误不附带宿主路径。Skill HTTP 适配层用 `{code, message}` 返回可展示的校验错误，前端公共请求层维持脱敏规则，Skill 界面统一读取业务 message。解析器、安装来源、路由与前端分别拥有格式、文件持久化、协议及展示行为。

## 替代方案

- 要求用户手改 ZIP：无法满足常见外部包直接导入的目标。
- 放宽机器标识为任意展示名：改变路径和引用约束，扩大影响范围。
- 读取 `_meta.json`：需要新增外部包元数据契约，本修复只采用名称派生。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 缺 slug 的展示名可导入，最终文件保留名称和标识 | 仍直接校验 name 或冲突覆盖展示名 | package.py、安装服务 | `test_skill_service.py` 与 `test_skill_display_name_import.py` 的共享/个人安装、数据库及文件回读 | 显式非法 slug 拒绝 | Passed |
| 标识未变时不改文件修订 | 无条件重写 frontmatter | package.py | 显式和旧式标识的 CRLF、注释字节比较，以及只编辑 notes 后根文件不变 | 无条件重写时用例失败 | Passed |
| 用户看到具体校验原因 | detail 形状不匹配或 UI 渲染对象 | Skill 路由、base.js、Skill UI | 路由与前端 unit、真实页面上传错误及中文包安装 | 非业务错误仍脱敏 | Passed |

## 后果

拼音与规范化可能重名；共享安装分配可用后缀，个人安装保留既有同名拒绝规则。显式填写 slug 是跨系统保持同一标识的方式。Skill 路由错误对象对读取字符串 detail 的调用方有兼容影响，所有仓库内 Skill UI 调用点须同步适配。

验证入口为 `docker compose exec api uv run --no-sync --group test pytest test/integration/api/test_skill_display_name_import.py -q`，用例自行清理创建的 Skill 与草稿，不依赖历史会话清理。前端 `api_boundary.test.js` 断言业务 message 和非业务错误脱敏；真实浏览器验证上传错误文案及中文包安装流程。
