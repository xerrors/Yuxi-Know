# 其他配置

## 内容安全

系统内置内容审查机制，保障服务内容的合规性。目前配置了关键词过滤以及 LLM 对内容进行审查。管理员可在 `设置` → `基本设置` 页面中进行配置并选择安全模型。

敏感词词库位于 `src/config/static/bad_keywords.txt` 文件，每行一个关键词，实时生效，无需重启服务。

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
- Web 界面: http://localhost:5173
- API 文档: http://localhost:5050/docs
- Neo4j 管理: http://localhost:7474
:::
