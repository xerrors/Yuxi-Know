# 文档处理与 OCR

本页供管理员选择 OCR、配置解析服务并排查文档产物。文档解析生成包含 `document.md` 和引用图片的完整目录，图片使用相对路径。知识库把目录发布到 MinIO 后索引；聊天附件随 Input 提交后准备到当前 Project Workdir，Agent 的 OCR 工具也在 Workdir 中生成解析目录。

文件状态和存储归属见[知识库机制详解](../mechanisms/knowledge-base.md)，第一次上传文档见[创建并使用知识库](../intro/knowledge-base.md)。

## 支持的文件

知识库上传接口当前支持：

- 文本：`.txt`、`.md`、`.html`、`.htm`、`.json`、`.csv`；
- Office：`.docx`、`.pptx`、`.xls`、`.xlsx`；
- PDF：`.pdf`；
- 图片：`.jpg`、`.jpeg`、`.png`、`.bmp`、`.tiff`、`.tif`、`.webp`；
- ZIP：压缩包内必须包含 UTF-8 编码的 `.md` 文件。

Office 文件使用本地转换：`.docx`、`.pptx`、`.xlsx` 由 Docling Slim 提取正文与图片，`.xls` 使用 pandas + xlrd 保留工作表内容。图片文件必须启用 OCR；PDF 选择 `disable` 时读取文本层，扫描版 PDF 通常得不到内容。

ZIP 优先选择名为 `full.md` 的文件，否则选择按路径排序的第一个 `.md`，并按完整路径提取正文引用的资源。绝对路径、`..`、重复归档路径、符号链接和缺失图片均拒绝整个结果。解析失败时回收输出目录。

## 从 URL 导入网页

网页导入受白名单控制。设置 `YUXI_URL_WHITELIST` 后，系统才会抓取 URL，并把 HTML 转成 Markdown 进入同一套知识库处理流程：

```bash
YUXI_URL_WHITELIST=github.com,docs.example.com,*.wikipedia.org
```

列表以逗号分隔；配置的域名及其子域名可以通过校验，空列表表示关闭 URL 导入。抓取器逐跳验证重定向白名单，最多跟随 5 次重定向，只接受 HTML，响应体默认不超过 10 MiB。每次连接只解析一次 DNS，拒绝包含非公网地址或已知云元数据地址的解析结果，并连接同一组已校验 IP；DNS 失败或无可用地址时直接失败。生产部署仍需按业务配置网络出口限制，抓取边界由 [url_fetcher.py](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/knowledge/utils/url_fetcher.py)拥有。

这组白名单用于知识库的 `/api/knowledge/files/fetch-url` 导入。Agent 的 `web_fetch` 通过 Tavily 或 DeepSeek 的固定官方接口读取网页，使用独立的[网络搜索配置](./configuration.md#网络搜索与网页正文)，不经过知识库导入抓取器。

## 选择 OCR 方案

| 引擎 | 运行位置 | 输出和适用场景 |
| --- | --- | --- |
| RapidOCR | 本地 CPU | 轻量图片/PDF 文字识别，默认方案 |
| MinerU | 本地 GPU 服务 | 复杂 PDF、表格和版面分析，输出 Markdown |
| MinerU Official | MinerU 云服务 | 不在本机部署 GPU，使用官方解析服务 |
| PP-Structure-V3 | 本地 GPU 服务 | 表格、票据和版面解析 |
| DeepSeek OCR | SiliconFlow API | 使用 SiliconFlow 的 DeepSeek OCR 模型 |
| PaddleOCR-VL-1.6 | 百度 AI Studio 云服务 | 文档版面解析，输出 Markdown |
| PP-OCRv6 | 百度 AI Studio 云服务 | 基础 OCR，输出纯文本 |

系统内部引擎 ID 为 `rapid_ocr`、`mineru_ocr`、`mineru_official`、`pp_structure_v3_ocr`、`deepseek_ocr`、`paddleocr_vl_1_6` 和 `paddleocr_pp_ocrv6`。页面中的健康状态只表示配置或服务探测结果，真正解析时仍会验证凭证和接口。

## 在页面配置

管理员进入“设置 → OCR 配置”可以设置默认引擎，并配置自托管服务地址或云端凭证。OCR 配置定义由 documents 模块拥有，system 模块统一管理持久化、脱敏和缓存。知识库上传和附件解析时可以单独选择引擎；没有单独选择时，使用系统默认值。

配置字段的读取规则是：数据库中保存的非空值优先，数据库没有值时读取对应环境变量。保存为空会清除数据库值并回到环境变量。API 不会回显环境变量中的密钥；数据库凭证只显示脱敏预览。

## 配置各类引擎

### RapidOCR

RapidOCR 随 API/worker 安装，第一次实际解析时加载 ONNX 模型。默认模型目录由 `RAPIDOCR_MODEL_DIR` 指定；没有设置时使用容器缓存目录。它不需要单独启动服务，但首次解析可能需要下载模型。

### MinerU

开发 Compose 已提供 `mineru-api`，它属于 `all` profile，端口为 `30001`，解析端点是 `/file_parse`：

```bash
docker compose --profile all up -d --build mineru-api
```

API/worker 在 Compose 中默认使用 `MINERU_API_URI=http://mineru-api:30001`。如果显存不足导致 MinerU 启动失败，可以在 `docker-compose.yml` 的 `mineru-api.command` 中启用并调整：

```yaml
# --gpu-memory-utilization 0.5
```

该参数用于减小 vLLM KV cache；仍然不足时可以继续尝试 `0.4` 或更低值。模型下载和其余显存参数以 `docker/mineru.Dockerfile` 与 Compose 为准。解析超时可以用 `MINERU_TIMEOUT` 调整，或在单次处理参数中传入 `timeout_seconds`。

### MinerU Official

在[官方服务](https://mineru.net)申请 API Key，放入 API/worker 的环境：

```bash
MINERU_API_KEY=<your-mineru-api-key>
```

页面中配置也可以保存该凭证；生产环境优先使用环境变量。该服务会把文件发送到外部服务，请先确认数据合规和供应商条款。

### PP-Structure-V3

开发 Compose 的 `paddlex` 服务属于 `all` profile，默认在容器内的 `8080` 端口提供版面解析：

```bash
docker compose --profile all up -d --build paddlex
```

API/worker 默认使用 `PADDLEX_URI=http://paddlex:8080`。本地 GPU 和镜像构建要求以 Compose 为准。

### DeepSeek OCR

在“智能体 → 模型供应商”中启用 `siliconflow-cn` 并配置凭证。DeepSeek OCR 会复用该供应商的 API 地址和 API Key，不接受单独的 OCR 凭证配置。

### PaddleOCR API

在[百度 AI Studio Access Token 页面](https://aistudio.baidu.com/account/accessToken)获取 Access Token：

```bash
PADDLEOCR_API_TOKEN=<your-paddleocr-token>
PADDLEOCR_API_URL=https://paddleocr.aistudio-app.com/api/v2/ocr/jobs
```

`PADDLEOCR_API_URL` 可省略，默认使用上面的地址。`PaddleOCR-VL-1.6` 和 `PP-OCRv6` 共用这组配置；前者输出 Markdown，后者输出纯文本。

## 分块参数和配置快照

知识库的分块配置由两部分组成：`chunk_preset_id` 表示策略，`chunk_parser_config` 保存该策略的具体参数。文件级 `processing_params` 会保存本次使用的 `ocr_engine`、分块策略和参数快照；OCR 服务地址和凭证在执行时读取，不写入文件快照。

修改分块策略不会自动重写已经索引的文件。要让旧文件使用新策略，需要重新解析或重新入库，并在最后确认文件状态和检索结果。

## 图片访问

知识库发布阶段把图片保存到私有 `kb-images` bucket，通过带知识库权限校验的后端路径访问。图片与 Markdown 按文档和解析尝试归属，持久化新结果后回收旧产物；失败只回收本次尝试，删除文档回收该文档的全部解析资源。不要把 MinIO 对象地址直接写成公开 URL，也不要为方便预览而开放整个 MinIO 管理端口。头像等公开图片使用 `/minio/public/...` 同源只读代理，二者边界不同。

Web 的 PDF/图片预解析先保存在用户隔离的临时目录，原文件草稿保存在 MinIO。发送时在 Input 接收事务绑定草稿，随后把原文件及已有解析目录准备到 Project Workdir；就绪提交后回收草稿来源，消费时再绑定正式 Message。未就绪输入不能开始执行。正式图片通过当前 Thread 的鉴权 artifact 接口读取，完整时序和调用格式见[图片与文件附件](./agents-public-api.md#图片与文件附件)。

草稿删除只清理尚未绑定的来源；正式附件在输入已消费或取消、文件已就绪且会话没有活动 Run 时才允许删除。正式删除先提交记录删除，再清理原文件和该附件的解析目录；清理失败时记录已删除，需要按日志处理剩余文件。

## 文件限制与排查

- 知识库和工作区单个上传文件最大 100 MiB；聊天文件草稿使用独立的 5 MiB 上限，不适用工作区上传上限。
- 工作区一次最多上传 50 个文件；知识库批量处理使用任务和页面限制。
- Agent 的 `read_file` 直接读取 UTF-8 文本和图片；PDF、Office 或其他二进制文件先用 `ocr_parse_file` 生成 Markdown。
- OCR 服务不可用时，先在 OCR 配置页查看健康状态，再检查容器日志、API 地址和凭证。
- 解析完成不等于索引完成；回到知识库文件列表确认 `parsed` 或 `indexed`，再做检索验证。

详细变量和容器映射见 `.env.template`、`docker-compose.yml` 和 `docker-compose.prod.yml`。文档页面只保留影响操作的配置，避免与配置文件维护两份默认值。
