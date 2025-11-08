# 其他配置

## 内容安全

系统内置内容审查机制（默认是关闭状态），保障服务内容的合规性。目前配置了关键词过滤以及 LLM 对内容进行审查。管理员可在 `设置` → `基本设置` 页面中进行配置并选择安全模型。

检测流程为，接收到用户输入之后，就对用户的输入进行检测是否合规，同时在流式传输的过程中进行实时检测（仅关键词）。当流式输出结束之后，则开始检测整个内容。
**注意**，使用 LLM 检测虽然可以大大缓解提示词注入带来的问题，但也会在用户交互上带来延迟影响，需要考虑是否启用。

对于关键词检测，敏感词词库位于 `src/config/static/bad_keywords.txt` 文件，每行一个关键词，实时生效，无需重启服务。

对于 LLM 检测，Prompt 可以看到 `src/plugins/guard.py`：

<<< @/../src/plugins/guard.py#guard_prompt

## 网页搜索

系统内置了基于 Tavily 的联网搜索能力，配置完成后，大模型会自动在需要时调用 `enable_web_search` 对应的工具，为回答提供实时网页信息。


1. 前往 [Tavily 官网](https://app.tavily.com/) 注册并在控制台创建 API Key。
2. 在项目根目录的 `.env`（或 `docker-compose.yml` 中的对应环境变量段）写入：
   ```env
   TAVILY_API_KEY=sk-xxxxxxxxxxxxxxxx
   ```
3. 重新加载服务使密钥生效，推荐执行：
   ```bash
   docker compose up -d api-dev web-dev
   ```
   若服务已运行，则使用 `docker compose restart api-dev` 即可。

完成以上步骤后，后端会自动将 `enable_web_search` 标记为启用，在智能体的工具配置区域即可看到这个工具，展示 Tavily 返回的实时结果。若需要关闭该能力，删除或清空 `TAVILY_API_KEY` 后再次重启服务即可。

## 服务端口

系统使用多个端口提供不同服务，以下是完整的端口映射：

| 端口 | 服务 | 容器名称 | 说明 |
|------|------|----------|------|
| **5173** | Web 前端 | web-dev | 用户界面 |
| **5050** | API 后端 | api-dev | 核心服务 |
| **7474/7687** | Neo4j | graph | 图数据库 |
| **9000/9001** | MinIO | milvus-minio | 对象存储 |
| **19530/9091** | Milvus | milvus | 向量数据库 |
| **30000** | MinerU | mineru | PDF 解析（可选）|
| **8080** | PaddleX | paddlex-ocr | OCR 服务（可选）|
| **8081** | vLLM | - | 本地推理（可选）|

::: tip 端口访问
- Web 界面: `http://localhost:5173`
- API 文档: `http://localhost:5050/docs`
- Neo4j 管理: `http://localhost:7474`
:::
