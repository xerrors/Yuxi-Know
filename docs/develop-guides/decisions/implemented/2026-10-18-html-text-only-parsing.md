# HTML 显式正文提取

状态：implemented
类型：feature
Owner：backend/yuxi/infrastructure/document_parsing/parser.py

## 问题

离线 HTML 可以保留完整正文，但引用未随文件上传的站点图片。严格图片完整性检查会拒绝这些文件，管理员需要显式选择只提取正文，同时保留上传的 HTML 原件。

## 决策

### 实现方案

单文件处理参数 `html_text_only` 默认为 `false`，只接受布尔值，只作用于 `.html` 和 `.htm`。知识库现有文件参数持久化与 documents service 把它传入统一解析器；解析器在 Markdown 转换前将每个 `img` 替换成其 `alt` 文本，同时移除 `video` 的 `poster` 属性，保留视频替代正文和视频链接，不读取或下载图片。安装的 Markdown 转换器通过这两类节点生成图片引用。默认转换仍复制全部本地图片并执行路径和完整性检查。原 HTML、其他格式、OCR 配置和页面操作保持原有归属。

## 替代方案

- 修改原件或上传时改写 HTML：改变原文件和内容哈希，损害来源核验。
- 缺图时静默跳过：调用者无法区分完整解析和图片丢失。
- 默认放松图片或路径检查：削弱现有完整性和隔离契约。

## 后果

正文提取不包含图片像素中的文字或图表内容；图片的 `alt` 只代表原 HTML 提供的替代文本。管理员显式选择该参数，索引结果仍需按文件状态和检索验证。原 HTML 与其内容哈希保持不变。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 显式正文提取保留前后正文和图片替代文本 | 图片链接导致失败或资源访问 | parser HTML 分支 | parser artifact unit，回读 Markdown 与原文件 | 原 HTML 分支因读取缺图被测试拒绝 | Passed |
| 显式正文提取保留视频替代正文和链接，poster 不产生图片引用 | 视频封面重新引入缺失或越界图片 | parser HTML 分支 | HTML/HTM、视频直链与 source 子节点、相对/绝对/远端/无 poster 回归，禁止额外文件与网络读取 | 恢复 video poster 后，正文模式因图片资源 guard 拒绝完成 | Passed |
| 默认完整性与路径检查保持有效 | 默认缺图或越界被接受 | parser 与 artifacts | 默认缺图、越界、有效图片及 Markdown/ZIP/Office 回归 | 缺图和越界输入必须拒绝输出 | Passed |
| 参数保留且严格接受布尔值 | 参数丢弃或字符串开启功能 | 知识参数归一化与 parser | 参数传递和非布尔值用例 | 字符串、数字、空值和容器值必须拒绝 | Passed |

相关测试命令：

```bash
docker compose exec api uv run --group test pytest test/unit/knowledge/test_parser_artifacts.py test/unit/knowledge/test_document_parser.py test/unit/knowledge/test_kb_utils.py test/unit/knowledge/test_parser_capabilities.py
```

文件参数归一化、documents service 和本地解析器由同一测试调用链覆盖；HTTP、worker 与 MinIO 的实际入库结果由部署后的导入验证补充。
