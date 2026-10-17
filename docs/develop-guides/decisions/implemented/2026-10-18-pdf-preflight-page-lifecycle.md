# PDFium 原生调用串行化与页面资源关闭

状态：implemented
类型：bug-fix
Owner：backend/yuxi/infrastructure/document_parsing/pdf_utils.py

## 问题

PDF 页树预检加载每个 PDFium 页面后依赖文档结束时关闭或垃圾回收释放。页面对象的循环引用可以被另一个线程的 GC 回收；该线程关闭原生页面时，预检线程仍在加载后续页面，产生 PDFium 原生内存损坏并终止 worker。后台作业和附件解析还可以同时处理不同 PDF，而 PDFium 对不同文档也不支持跨线程同时调用。持久作业随后以租约失效收敛，但原生崩溃会影响该进程的其他执行。

## 决策

### 实现方案

`pdf_utils.py` 拥有唯一共享 `PDFIUM_LOCK`。页树预检在同一锁内加载、检查并逐页显式关闭页面，随后关闭文档。RapidOCR 和 DeepSeek OCR 使用同一把锁打开文档、获取页数、渲染页面及关闭原生资源；它们通过共享渲染函数将图像复制为独立 PIL 数据，再释放 bitmap 和页面，耗时 OCR 和网络请求在锁外执行。正常与异常路径都显式关闭页面、bitmap 和文档，避免其他线程的 GC 延迟释放原生资源。

尺寸读取失败仍记录相应页槽并返回已有结构错误；PDF 格式、页数、OCR 选择和原文件字节保持既有契约。实现不新增部署配置或解析调度器。

## 替代方案

- 依赖 `doc.close()`：无法阻止循环引用在遍历中由其他线程提前回收页面。
- 禁用进程 GC：改变整个 worker 的内存管理，扩大影响范围。
- 只关闭页面：解决延迟 GC，但不能阻止不同文档的显式原生调用重叠。
- 为整份 OCR 文档持锁：实现简单，但会在模型推理和网络等待期间阻塞其他文档。本实现只保护原生资源访问与复制。

## 后果

页面读取失败仍由预检汇总为结构异常；页面、bitmap 和文档的原生资源都在当前执行线程及共享锁内完成释放。并行文档的原生操作串行执行，OCR 推理和网络等待仍可并行；渲染图像复制增加单页内存与复制成本。新增本地 PDFium consumer 必须使用同一并发边界并显式结束资源生命周期。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 正常页和读取失败页由预检线程释放 | 异线程 GC 延迟释放原生页 | `pdf_utils.py` | `test_pdf_preflight.py` 的真实 PDFium 页面生命周期测试 | 恢复隐式关闭后，两个参数用例都因 GC 线程释放真实页面而失败 | Passed |
| 现有 PDF 仍完整提取全部页面 | 原生崩溃或截页 | PDF 预检与统一 parser | 无网络隔离容器内的长文档完整提取及十轮 GC 压力对照 | 旧预检与并行 GC 触发原生 abort | Passed |
| 三个 consumer 不会跨线程重入原生 PDFium | 不同文档并发产生伪页损坏或 native abort | 共享锁与两个 OCR engine | `test_pdfium_engines.py` 的四组真实原生调用重入 oracle | 临时移除共享锁后，四组 consumer 组合都因原生重入失败 | Passed |
| 图像脱离已释放的 bitmap，异常仍关闭资源 | use-after-free、文档或页面泄漏 | 共享渲染函数与两个 OCR engine | 强制共享 RGBX / RGBA bitmap 并验证共享像素随缓冲区变化，释放前覆写缓冲区，再锁外读取复制图像；两个 OCR engine 的正常、页数、渲染、OCR 异常共八例 | 移除显式复制后无法保留可读取的原像素；未清理时原生对象仍有效 | Passed |

相关单测命令：`docker compose exec api uv run --group test pytest test/unit/knowledge/test_pdf_preflight.py test/unit/knowledge/test_pdfium_engines.py test/unit/knowledge/test_parser_engines.py test/unit/knowledge/test_document_parser.py`。正常、异常和跨 consumer 并发共 35 个用例通过。无网络、只读语料、无业务状态挂载的隔离容器中，705 页长文档完整文本提取成功；旧预检遇并行 GC 时触发原生 abort，逐页显式关闭后相同压力连续十轮成功；共享锁下两个预检线程与并行 GC 连续验证 14,100 个页槽成功。

[pypdfium2 官方线程约束](https://pypdfium2-team.github.io/pypdfium2/python_api.html#incompatibility-with-threading)说明不同文档也不能在多个线程中同时调用 PDFium；共享锁覆盖仓库当前三个原生调用入口，资源显式关闭同时避免自动终结器绕过该边界。
