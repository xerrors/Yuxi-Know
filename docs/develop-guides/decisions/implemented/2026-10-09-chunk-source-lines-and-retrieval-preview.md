# Chunk 原文行号与检索定位预览

状态：implemented
类型：feature
Owner：backend/yuxi/modules/knowledge/chunking/dispatcher.py

## 问题

检索结果具有 chunk_index，但缺少持久化的原文起止行号。用户无法从命中片段定位到完整解析文本，检索页面也没有并排查看原文的交互。

## 决策

### 实现方案

入库切分以保存的完整解析文本为唯一行号基准，使用 1-based、两端包含的 start_line/end_line。SourceText 在切片、合并、重叠及超长分片时携带字符来源，生成标题和问答前缀不计为原文；重写的 Markdown 块使用 parser 的 token 范围，HTML 表格转键值对与 CSV 解码后的子块定位到完整原始块或 record。dispatcher 只投影已有来源，缺少来源时显式失败。KnowledgeChunk 在 PostgreSQL 保存行号，检索从同一 active generation 的 PG Chunk 补齐 metadata，Agent、Public 工具与检索测试共用该结果。

MarkdownPreview 增加块级原文行映射与高亮定位；MarkdownDocumentPreview 提供 Markdown/源码视图，源码显示逐行行号和高亮。文件详情弹窗及检索侧栏复用该组件。页面默认 800px 居中，选中 Chunk 后 Flex 等分两栏，窄屏纵向排列。侧栏加载完整解析原文，文档内容接口用 line_location 标识全文、已入库状态与快照代次是否自洽；不可定位时显示原因并清空高亮。新查询、清空结果与切库均使旧检索请求失效并清理选择，过期请求不得覆盖新结果或新文件。检索方式及文本过滤统一使用已有检索配置面板保存的参数，移除检索页内的重复入口。

新增行号列进入 Knowledge schema v3；schema-init 只在空库建立当前结构，API/worker 只读校验版本。部署接受停机清库和重新导入文档，旧版本数据库不提供升级或回填路径；清库需要明确的数据删除授权。

## 替代方案

- 检索时反查片段文本计算行号：重复读取全文，重叠、重复正文与格式重写存在歧义。
- 仅显示 Chunk 内容：不能完成完整原文的上下文定位。
- 独立实现新的文件预览：重复已有 Markdown 渲染与文档加载边界。
- 为旧库提供 v2→v3 行号迁移：部署明确接受清库重新开始，历史兼容没有当前验收需求。

## 后果

旧版本数据库会被启动版本门禁拒绝；重建需清空所属环境的数据库及关联知识存储，再由 schema-init 建立当前结构并重新创建账号、导入文档。切分器的字符串操作必须保留来源映射，CSV 和重写表格采用块范围，接受较宽的定位区域。定位 Markdown 使用原始文本渲染，保持行数；普通无定位预览保持已有 HTML/SVG 展示方式。外部只读知识库由其提供方拥有原文定位。

## 验证

切分与 Milvus 相关 unit 65 项通过，后端非 slow unit 2539 项通过、55 项跳过，真实 HTTP 与 schema integration 31 项通过，真实 worker/HTTP/PG/MinIO/Milvus E2E 1 项通过；后者验证多行持久行号、三种检索模式、重建与删除后的最终状态。前端 lint、502 项 unit、TypeScript/Vite build 和文档 build 通过；工程契约检查及其 64 项 unit 通过。

负向验证恢复来源缺失时的静默定位及旧检索结果竞态，相关断言在预期原因上失败；修复后通过。浏览器核对 Markdown/源码行号、跨文件切换、过期响应、无定位提示、关闭预览、桌面等分双栏与窄屏排列。

标准后端测试命令在同步依赖时遇到既有 egg-info 权限问题，因此使用同一容器已有环境加 --no-sync 执行测试。真实 worker/HTTP/PG/MinIO/Milvus E2E 使用测试 embedding replay 服务，不证明商业 embedding 或 reranker 服务可用性。测试中 PostgreSQL 曾进入恢复且 API 不响应，服务恢复后重新执行验收，不将环境故障记录为通过。
