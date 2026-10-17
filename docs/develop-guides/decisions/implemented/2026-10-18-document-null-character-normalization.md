# 解析正文的 NUL 字符归一化

状态：implemented
类型：bug-fix
Owner：backend/yuxi/infrastructure/document_parsing/parser.py

## 问题

文档提取器可以返回含 U+0000 的有效 Python 字符串。Markdown 对象写入成功后，普通分块器保留该字符，PostgreSQL 的文本编码边界拒绝整个分块批次，文件无法完成索引。语义分块器已经使用 U+FFFD 替换 NUL，但该局部处理没有覆盖其他分块入口。

## 决策

### 实现方案

统一文档解析入口在发布 `document.md` 前，将正文中的每个 U+0000 替换为一个 U+FFFD；其余字符、换行及资源路径校验保持原语义。单字符替换保留正文字符位置，所有格式和分块预设消费同一份可持久化 Markdown。原始文件和对象字节不变。该规则与现有语义分块器的 NUL 替换规则一致。

## 替代方案

- 在各分块器或 repository 中分别清理：解析对象与分块事实可能不一致，并复制格式归一化规则。
- 删除 NUL：改变后续字符位置，削弱来源范围与原解析正文的对应关系。
- 拒绝包含 NUL 的原始文档：原件可读取且其他正文有效，无法满足完整解析与入库需求。

## 后果

U+FFFD 表达无法表示的原字符，并非还原未知字形；原始文件仍负责保留原字节。已经发布的 Markdown 不被后台修改，既有派生结果需显式修复或重新生成后再索引。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| TXT、Markdown 与提取器输出只替换 NUL，保留其余正文及原件字节 | 修复只覆盖单个分块器或删掉相邻文本 | 统一 parser | `pytest test/unit/knowledge/test_document_text_nulls.py -q`，3 passed | 在独立临时容器移除发布前替换，3 个用例均因正文仍含 NUL 断言失败 | Passed |
| 解析正文可经过真实 PostgreSQL 文本协议往返 | 文件输出成功但持久化仍拒绝 | parser 与 PostgreSQL 驱动边界 | `pytest test/integration/services/test_document_text_nulls.py -q`，1 passed | 原始带 NUL 字符串经同一协议因 UTF8 的 `0x00` 被拒绝；解析后的文本往返一致 | Passed |

上述测试在只读挂载当前源码的临时应用镜像容器内执行，PostgreSQL 用例仅使用参数化 `SELECT` 和回滚，不修改已有业务数据。移除修复的负控使用独立文件覆盖挂载，源码保持原值。既有派生结果的修复与索引仍需部署后的真实业务回读，不能由该协议往返测试替代。
