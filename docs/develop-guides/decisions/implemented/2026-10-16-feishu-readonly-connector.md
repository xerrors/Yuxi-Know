# 飞书知识库在线检索与阅读

状态：implemented
类型：feature
Owner：backend/yuxi/modules/knowledge/implementations/feishu.py

## 问题

用户需要在 Yuxi 搜索飞书知识空间并读取普通文档的当前正文，不需要同步、解析或向量入库。飞书搜索要求用户凭证，文档管理与在线阅读需要分别表达能力。

## 决策

### 实现方案

FeishuKB 使用管理员配置的用户 token 与空间 ID 调用原生 Wiki 搜索，返回新版普通文档（Docx）的标题和节点 ID。读取先重新解析节点，核验空间归属、文档类型及快捷方式，再获取纯文本正文并按行分页。请求采用固定飞书 API 域名，不缓存文档权限或正文，不创建 KnowledgeFile、解析产物或本地索引。

KnowledgeExecutor.supports_document_read 独立于本地文档管理能力 supports_documents。Manager.open_document 向 executor 提供本次知识库配置；本地 executor 复用原有窗口读取，飞书实现远端正文读取。Agent 与现有 Public 查询入口复用知识库授权，飞书上传、解析、文件树、下载和文内查找仍然拒绝。

连接凭证归知识库配置所有。管理员通过 Yuxi 共享权限授予使用者访问这一连接，使用者不自动映射为自己的飞书身份。响应和配置日志不回显 token；编辑时留空保留原值，填写新值替换。不提供产品内 OAuth 登录或自动刷新。上游错误经现有领域错误契约返回脱敏原因，凭证到期需要管理员更换。

前端以正文阅读能力区分可进入详情的飞书连接与仅检索的 Dify/Notion 连接，列表入口、详情直达和面板展示使用同一能力判断，文档管理门禁保持独立。前端沿用动态创建表单；飞书检索结果点击标题后在只读面板展示正文，支持分页和读取失败重试。配置页面支持更新空间和凭证。正文作为普通文本显示，保留字符而不执行 HTML。

## 替代方案

- 应用身份同步后本地检索：需要同步状态、删除对账及索引维护，超出当前需求。
- 用户 OAuth 和自动刷新：适合长期每用户访问，当前采用手动配置用户凭证。
- 把在线阅读标为支持文档管理：会错误开放上传、解析和文件树入口。

## 后果

用户 token 过期需人工更换。搜索与阅读分别鉴权，撤权、删除和类型变化可使候选文档读取失败。搜索返回文档候选，不包含伪造的分块正文或相关性分数。阅读范围为新版普通文档的正文文本，旧版文档、表格、附件、快捷方式和富文本完整还原不在当前范围。

共享连接表示使用其配置身份的飞书权限；管理员需要按实际资料共享范围配置 Yuxi 读取权限。空间限制在 executor 的远端读取边界执行，不能通过直接传入其他空间的节点绕过。

## 验证

- `docker compose exec -T api uv run --group test pytest test/unit -m 'not slow'`：Passed，2703 passed、61 skipped、7 subtests。
- `docker compose exec -T api uv run --group test pytest test/unit/plugins/test_feishu_kb.py test/unit/plugins/test_dify_kb.py test/unit/toolkits/test_kbs_tools.py -q`：Passed，61 passed；覆盖分页、跨空间与快捷方式拒绝、凭证隔离、实时正文、非法输入和错误脱敏。
- `docker compose exec -T api uv run --group test python -c ...`，容器中执行 `pytest.main(["test/integration/api/test_feishu_connector.py", "-q", "--tb=short"])`：Passed，2 passed；真实用户测试凭证只通过进程标准输入注入测试环境，验证创建、原生搜索、正文阅读、权限拒绝、配置更新与 token 保留，并从 PostgreSQL 回读文件记录为零。测试自管其知识库和用户，不清理其他测试资源。
- `docker compose exec -T frontend pnpm run lint:check`、`pnpm run test:unit`、`pnpm run build`：Passed，前端单测 629 passed。
- `playwright-cli -s=feishu-ui run-code --filename=frontend/test/browser/feishuConnectorReading.js`：Passed；真实浏览器使用确定性 HTTP fixture 验证搜索、阅读、分页、纯文本、键盘打开、错误重试及浅深色 1440/768 宽度。该验证不等同于真实飞书的完整 Web 创建和编辑链路。
- `pnpm --dir docs run build`：Passed。工程契约、脚本单测、Ruff 与 `git diff --check` 在最终交付前检查。
- 独立 Reviewer 审查源码、权限边界、凭据处理、测试与文档，无待处理问题。真实飞书撤权及全类型读取未执行；权限变化由协议层负向测试覆盖，正文更新由下述真实网页链路验证。

导航补充验证：`playwright-cli -s=feishu-ui --raw run-code --filename=frontend/test/browser/feishuConnectorNavigation.js` 使用固定 HTTP 夹具通过真实页面验证卡片导航、详情直达、查询面板可见及上传隐藏。另以用户授权的测试身份，实际通过飞书网页创建仅成员可见的测试知识库、保存普通文档并在 Yuxi 网页创建指定用户可读的连接；真实搜索和正文阅读验证 V1 后，在飞书改为 V2 并重新打开确认持久化，Yuxi 重新读取获得 V2。PostgreSQL 回读本地文件记录为零。凭据、空间标识及用户资源地址不写入仓库。
