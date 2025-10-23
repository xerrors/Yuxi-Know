# 常见问题

以下为最常见的安装与使用问题，更多细节请参阅相应章节链接。

- 首次运行如何创建管理员？
  - Web 首次启动会引导初始化；也可调用 API：
    - `GET /api/auth/check-first-run` → `first_run=true` 时
    - `POST /api/auth/initialize` 提交 `user_id` 与 `password`
  - 无默认账号，初始化后使用创建的超级管理员登录

- 镜像拉取/构建失败？
  - 可使用 `docker/pull_image.sh` 辅助拉取，或配置代理环境变量 `HTTP_PROXY/HTTPS_PROXY`
  - 若已配置代理仍失败，可临时取消代理后重试
  - 参考：介绍 → 快速开始 → 故障排除

- 服务端口与访问地址？
  - Web: `http://localhost:5173`；API 文档: `http://localhost:5050/docs`
  - 端口一览与说明见：高级配置 → 其他配置 → 服务端口

- Milvus/Neo4j 启动或连接失败？
  - 重启：`docker compose up milvus -d && docker restart api-dev`
  - Neo4j 默认：用户名 `neo4j`、密码 `0123456789`、管理界面 `http://localhost:7474`

- OCR 模型或服务不可用？
  - RapidOCR 本地模型：确保 `MODEL_DIR/SWHL/RapidOCR` 下存在 `PP-OCRv4` 模型
  - MinerU/PaddleX：检查健康检查接口与 GPU/CUDA 版本
  - 参考：高级配置 → 文档解析

- 支持的文件类型与常见入库失败？
  - 查询：`GET /api/knowledge/files/supported-types`
  - 常见失败：不支持的扩展名、内容哈希重复（去重）、OCR 服务未就绪

- 批量上传与转换示例？
  - 上传入库：`uv run scripts/batch_upload.py upload --db-id <id> --directory <dir> --username <u> --password <p> --base-url http://127.0.0.1:5050/api`
  - 参考：高级配置 → 文档解析

- 登录失败被锁定？
  - 多次失败会临时锁定账户，请根据提示等待后重试

- 如何查看日志和状态？
  - `docker ps` 查看整体；`docker logs api-dev -f`、`docker logs web-dev -f` 查看服务日志
