# 统一网络搜索与网页抓取

状态：proposed
类型：feature
Owner：backend/yuxi/modules/extensions/web/services.py

## 问题

搜索供应商在进程导入时由环境变量决定，管理员无法在设置中切换，供应商结果的摘要与正文语义不一致，也没有独立网页抓取工具。

## 提案

### 实现方案

extensions 拥有三家独立敏感 Option、供应商适配和 Search/Fetch 用例。system 复用现有 PostgreSQL 配置表、脱敏和提交边界，保存两个默认供应商；设置值优先于环境变量。工具执行与管理员测试调用同一服务，每次调用读取有效配置，运行装配排除未配置能力。HTTP 路由只处理认证和协议；前端提供独立配置和默认项，凭据复用 OCR 的查看/编辑/取消/保存交互，留空保存清除；卡片右上角通过固定查询和文档一键测试，仅显示 Search/Fetch 通过或失败，不展示测试输入与正文。Search 支持 Tavily、DeepSeek、豆包 Custom；Fetch 支持 Tavily Extract、DeepSeek Fetch。显式选择失败不跨供应商重试。

## 替代方案

继续仅使用环境变量无法满足在线配置；全局与个人双层配置增加当前不需要的权限与费用归属；自建网页抓取需要承担额外网络和正文提取边界。采用独立 Fetch 选择避免把豆包搜索摘要当作任意 URL 正文。

## 验收标准

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 配置独立持久化且不泄露 Key | HTTP/数据库 | system Option、extensions web | HTTP integration 与数据库回读 | 非管理员、清除与环境回退、非法草稿凭据不回显 | Passed |
| 三家 Search、两家 Fetch 具有准确语义 | 供应商协议 | extensions web | 适配器单测、HTTP integration 与独立 TLS 协议重放 | 限制、无 Key、错误响应、非法 URL | Passed |
| 保存后 worker 使用新配置 | 跨进程运行 | 工具运行装配 | 确定性 E2E 与持久消息 | 未配置能力不绑定 | Not run |
| 设置可编辑、切换和测试 | DOM/交互 | 网络搜索设置页 | 前端 unit、build、浏览器 | 草稿测试不保存、失败不伪装空结果 | Passed |

## 风险

外部接口可能漂移，真实供应商探针需要凭据。本地 PostgreSQL/HTTP 与独立 TLS 协议重放通过，浏览器证据来自固定 HTTP 响应上的生产组件交互；完整 worker E2E 和真实供应商探针为 Not run，前者需要独立 Cube 槽位及测试账号，后者需要供应商凭据。worker E2E 由 system-tests.yml 在独立重放拓扑执行，证据收敛后再将记录移入 implemented。
