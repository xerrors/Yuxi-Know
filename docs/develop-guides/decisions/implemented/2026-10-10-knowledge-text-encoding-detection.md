# 知识库文本解析按用户编码解码

状态：implemented
类型：bug-fix
Owner：backend/package/yuxi/knowledge/parser/text_encoding.py

## 问题

统一解析器把所有纯文本输入按 UTF-8 严格解码：`txt`/`md`、`html`、`json` 用 `aiofiles.open(..., encoding="utf-8")`，`csv` 交给 pandas 的默认编码，ZIP 内 markdown 直接 `bytes.decode("utf-8")`。用户上传 GBK、GB18030、Big5、UTF-16 或 Latin 系编码的文件时，读取字节就抛 `UnicodeDecodeError`，文件被置为 `error_parsing` 并让整个入库任务失败，用户只能看到编解码器技术信息。

`chardet` 早已是后端依赖但从未被使用；同一代码库的其他路径（对话上下文、记忆、工作区读取）已使用 `errors="replace"` 或显式捕获解码错误，说明缺失只在解析链路这一处边界。

## 决策

### 实现方案

`yuxi.knowledge.parser.text_encoding.decode_user_text()` 是"用户上传文本字节 → 字符串"的唯一 Owner：先按 BOM 判定 UTF-8-SIG/UTF-16，再尝试 UTF-8 严格解码，失败后用 `chardet` 探测编码严格解码，仍失败则以同一编码做替换兜底并记录 WARNING。统一解析器的每个用户文本入口（`txt`/`md`、`html`/`htm`、`json`、`csv`）以及 ZIP 内 markdown 都改为读取字节后调用该函数；入口到结果的主链路（parse → parsed markdown → MinIO）不变，仅解码边界收敛到该函数。

自己写回 MinIO 的 parsed markdown 仍是 UTF-8 契约（`knowledge/base.py`、`attachment_service.py` 读取处），不属于本主张的输入面，未改动。

## 替代方案

- 拒绝非 UTF-8 上传并返回友好错误：拒绝。用户仍需自行转码，主链路继续失败，历史文件也无法重新解析。
- 保存原始字节并记录检测到的编码，供后续重解码：拒绝。改动持久数据与 parsed markdown 契约，超出缺陷本身。
- 一律 `errors="ignore"` 或 `errors="replace"` 而不探测：拒绝。GBK 内容会稳定产出乱码，且丢掉可恢复的可读性。

## 后果

- 解析不再因编码终止；探测错误时输出可能是乱码文本而非失败，兜底路径会产生 U+FFFD 并留下 WARNING 日志，可据此定位具体文件。探测置信度低于 0.5 时无论解码是否成功都记录低置信 WARNING；含 NUL 的输入跳过 UTF-8 快路径交给探测器（无 BOM UTF-16 若探测器仍误判，则属该残余失败面，UTF-32 不在承诺范围）。
- `csv` 改为解码后经 `StringIO` 交给 pandas，列类型推断行为由既有 dtype 测试约束。
- 文本解析路径新增对 `chardet` 的实际依赖（依赖已在 `backend/package/pyproject.toml` 中声明）。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 常见非 UTF-8 上传可解码为原文 | `UnicodeDecodeError` 终止入库 | text_encoding.py | `test_parser_text_encoding.py::test_decode_user_text_detects_legacy_codecs` | 同一断言先证明 `raw.decode("utf-8")` 必抛 `UnicodeDecodeError` | Passed |
| 带 BOM 的 UTF-8 不残留 BOM | BOM 字符进入索引 | text_encoding.py | `::test_decode_user_text_strips_utf8_bom` | 断言 `raw.decode("utf-8")` 结果以 `\ufeff` 开头 | Passed |
| GB18030 生僻字不丢 | 探测到 GB2312 后丢字 | text_encoding.py | `::test_decode_user_text_keeps_gb18030_only_characters` | 仅用 GB2312 字表覆盖的样本无法触发 | Passed |
| 残破二进制不终止解析 | 截断/二进制内容抛异常 | text_encoding.py | `::test_decode_user_text_keeps_readable_fragments_of_binary_upload`、`::test_decode_user_text_replaces_truncated_utf16_tail` | 截断 UTF-16 必须产生 U+FFFD 而非异常 | Passed |
| 无 BOM UTF-16 不走 UTF-8 快路径 | NUL 合法 UTF-8 字节导致快路径静默产出夹杂 NUL 的垃圾 | text_encoding.py | `::test_decode_user_text_routes_nul_bytes_to_detector` | 移除 NUL 嗅探后断言结果含 `\x00` 而失败 | Passed |
| 各扩展名的真实解析路径接受非 UTF-8 | 入口未接解码仍失败 | unified.py / zip_utils.py | `::test_parse_resolved_document_accepts_non_utf8_upload`（txt/md/html/json/csv）、`::test_process_zip_file_accepts_non_utf8_markdown` | 未接入解码时这些用例会以 `UnicodeDecodeError` 失败 | Passed |
| 后端单测无回归 | 既有解析行为漂移 | backend/test/unit | `pytest test/unit -m "not slow"` → 2490 passed / 62 skipped（含接入两项改动后全量） | 不适用 | Passed |

未验证范围：浏览器上传 + worker 入库的端到端链路（E2E 回放）`Not run`，以及乱码文件的量化质量对比。
