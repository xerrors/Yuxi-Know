import pytest
import numpy as np

# 现在可以安全地导入了，因为顶层不再有重型依赖
from yuxi.knowledge.chunking.ragflow_like.parsers import semantic
from yuxi.models import select_embedding_model

@pytest.fixture
def embed_fn():
    """使用真实的嵌入函数 (从 SiliconFlow 获取)"""
    model_id = "siliconflow/Qwen/Qwen3-Embedding-0.6B"
    try:
        model = select_embedding_model(model_id)
        def encode(sentences):
            if isinstance(sentences, str):
                sentences = [sentences]
            return model.encode(sentences)
        return encode
    except Exception as e:
        pytest.skip(f"无法初始化真实嵌入模型 {model_id}: {e}")

@pytest.fixture
def sample_markdown():
    """提供一个包含多章节、公式符号和复杂结构的临时 Markdown 样本"""
    return """
## 痛点与挑战

在传统的RAG知识库前置处理过程中，我们面临着诸多挑战：

- **格式繁杂兼容难**：企业文档格式多样，传统工具（例如python-docx和pymupdf）难以同时高质量处理 Office 文档和复杂的 PDF 扫描件。
- **语义割裂检索差**：简单的按字符切分导致上下文丢失，检索匹配度低，无法满足业务需求。
- **解析效率瓶颈**：面对海量存量文档，缺乏高并发处理能力，响应速度慢，难以支撑大规模应用。

## 技术方案概览

为了解决上述问题，我们构建了一套高性能、可扩展的文档处理架构：

- **全格式支持**：全面覆盖 **Word、Excel、PDF、PPT和图片**等主流办公文档格式。
- **高精度解析**：通过引入MinerU VLM模型实现准确的布局解析 and 元素提取。
- **跨平台支持**：同时支持**英伟达CUDA和华为CANN框架。**
- **知识库应用优化**：为了更好支持上层应用，解析后增加了智能切分和实体识别功能，增强后续的检索效果。
- **高并发架构设计**：
    - 采用 **FastAPI** 作为服务入口，保障请求的高效接收与响应。
    - 引入 **Celery** 分布式任务队列，实现请求响应与处理过程的完全解耦，有效应对流量洪峰，保障系统稳定性和可用性。
    - **资源利用最大化**：通过创建多组 **Celery Worker**（执行CPU密集任务） + **vLLM Server**（执行GPU密集推理任务）的Pod单元，实现对多核CPU+多卡GPU的并行调用，大幅提升单机处理吞吐量。
    - 使用Docker Compose进行服务编排，不同功能划分为不同的进程，保证服务的并发量和性能。

![image.png](attachment:393b3113-298b-4063-b572-db9694dddb4b:image.png)

## 架构设计

| 服务名称 | 容器名称 | 职责描述 |
| --- | --- | --- |
| **mineru-api** | `mineru-api` | **API 网关：**基于 FastAPI，提供对外 HTTP 接口 。负责接收请求、鉴权及任务分发。 |
| **mineru-worker** | `mineru-worker` | **异步任务处理器：**基于 Celery，负责 PDF 解析、OCR、文档转换等耗时任务。 |
| **vllm** | `mineru-vllm` | **推理后端：**运行 MinerU 视觉大模型 (VLM)，提供高并发的文档理解与提取能力。 |
| **redis** | `mineru-redis` | **消息中间件：**作为 Celery 的 Broker 和 Backend，同时缓存部分运行时数据。 |

## 核心技术亮点

### 1. 多模态融合的高精度解析

针对不同类型的文档，我们采用了差异化的解析策略，以确保最佳效果：
* **Office 文档**：利用 **Docling** ，快速、精准地从文件中提取文本与格式信息。
* **复杂 PDF 文档**：引入 **MinerU 视觉大模型（VLM）**，该模型具备类似人类的视觉能力，能够深度理解文档排版，完美还原文档结构和准确提取页面上的公式和表格元素，并统一输出为标准的 Markdown 格式。

![原始文件](attachment:45b43827-6c38-49ed-9996-e08c037d6858:公式1_1原始文件.png)

原始文件

![解析后效果](attachment:90e6a6da-0ac6-4b43-bfcb-f0921960c5f1:公式1_3解析后预览.png)

解析后效果

### 2. 智能表格处理

针对文档中的表格数据，我们提供了两种灵活的转换方式，满足不同应用场景的需求：
* **键值对转换**：将表格行列关系转换为自然语义表达，便于大模型理解和问答。并且**支持合并单元格的处理**，避免生成关系错乱的表格数据。例如，将”产品名称 | 价格 | 库存”的表格转换为”产品名称：A；价格：100元，库存：50件；产品名称：B；价格：150元，库存：30件”等键值对形式。
* **Markdown表格转换**：保持表格的原始结构，转换为标准的Markdown表格格式，便于上层应用中可视化展示。

![原始表格](attachment:b02cd061-728f-4fd8-ac12-5298dd427cc3:表格1_1原始文件.png)

原始表格

![markdown格式表格](attachment:efaa0df1-96d6-4c9f-bbb4-80a561d10009:表格1_3解析后预览.png)

markdown格式表格

![key-value格式表格](attachment:a476994c-6d6b-4a74-9a55-b6907ce40bde:表格1_4切分后.png)

key-value格式表格

此外，**针对过长的表格，支持按照长度切分，在不丢失信息的前提下**适配向量数据库的存储，保证后续的检索效果。

![原始表格](attachment:71523288-f21f-413e-a69b-e9fda14532e9:表格2_3解析后预览.png)

原始表格

![表格切分后](attachment:ffa664bb-5eb8-4820-a4fb-9968266e8fd2:表格2_4切分后.png)

表格切分后

### 3. 基于语义的智能切分

摒弃了传统机械的字数切分方式，我们引入了 **BGE Embedding 模型**。通过计算文本向量并利用相似度聚类算法，将含义紧密相关的段落自动聚合。这种方式确保了每一个数据切片都是一个完整的”语义单元”，大幅提升了后续检索的准确性。与此同时，模型规模为24M，资源占用率极小，对整体解析流程的影响微乎其微。

![语义切分前1](attachment:7e4e4c3c-126b-4c5b-8dc7-e4da93252a54:语义分析1_2解析后.png)

语义切分前1

![语义切分后2](attachment:3febe837-7722-4c59-8e40-25e9bc8dbbaa:语义分析1_4切分后.png)

语义切分后2

![语义切分前2](attachment:e17278be-b749-4618-8b51-793f83892caf:语义分析2_2解析后.png)

语义切分前2

![语义切分后2](attachment:18f40c6d-6c08-40e8-b369-927b33f09816:语义分析2_3切分后.png)

语义切分后2

### 4. 上下文感知的标题聚合

针对企业长文档层级复杂的特点，我们开发了**标题聚合功能**。系统会自动将多级标题信息聚合到对应的段落中。无论文档如何切分，每个切片都能保留”父级标题-子标题”的完整路径，有效解决了碎片化导致的上下文丢失问题，从而提升了后续检索的准确性和相关性。

![多级标题聚合](attachment:7dd756ee-b097-4b2c-b7ca-638915fd7b23:语义分析2_3切分后.png)

多级标题聚合

### 5. 关键信息自动提取

为了进一步提升检索效率，我们集成了中英文的 **NER（命名实体识别）模型**。在解析过程中，系统会自动抽取文档中的组织机构、人名、专有名词等关键实体，为文档打上”智能标签”，实现多维度的精准检索。

![image.png](attachment:62685770-d067-4df5-9415-a559b0e20658:image.png)

![image.png](attachment:4d3847f8-317d-4393-8e7c-bddb5f3c50f7:image.png)

### 6. 内容检索

![原始PDF页面](attachment:4ad6a991-7d23-494d-a653-95ec8ce24f75:image.png)

原始PDF页面

![搜索关键字“叶片描述”](attachment:cc341750-9fb0-4863-b758-d77194a783c1:image.png)

搜索关键字“叶片描述”

返回结果如下：

```json
{
    "status": "success",
    "message": "搜索成功",
    "data": {
        "result": [
            {
                "page_idx": 14,
                "span_range": [
                    0,
                    0
                ],
                "bbox": [
                    70,
                    586,
                    525,
                    614
                ]
            },
            {
                "page_idx": 14,
                "span_range": [
                    0,
                    0
                ],
                "bbox": [
                    69,
                    625,
                    147,
                    638
                ]
            }
        ]
    }
}
```

应用展示

![c17614a4ad447a787d3a1131825a2d22.png](attachment:0c3997f7-3107-43c9-8c90-b99b8283dbf7:c17614a4ad447a787d3a1131825a2d22.png)

### 7. 性能优化

通过将CPU密集型任务和GPU密集型任务切分为相互独立的进程，更好利用了高性能服务器的硬件资源，不仅可以进行多路解析，在单任务的处理上也有显著提升。在附加了实体识别和智能分段等附加功能，处理时间和使用MinerU CLI所需的时间几乎没有差别。在多路服务器上可以通过简单配置，使不同的任务使用服务器上独立硬件资源，成倍提速。

| 解析样例 | 原生MinerU | 本方案 |
| --- | --- | --- |
| PDF测试1（158页英文内容） | 79.26s | 79.661 |
| PDF测试2（731页英文内容） | 402s | 393s |
| PDF测试2（670页中文内容） | 163 | 116.53 |

测试环境：

- GPU: NVIDIA A100 80GB
- CPU: Intel(R) Xeon(R) Gold 6348 CPU @ 2.60GHz

## 核心组件

| 依赖名称 | 版本范围 | 功能描述 |
| --- | --- | --- |
| **fastapi** | `>=0.115.12` | **Web 框架**：提供高性能的 API 服务接口，支持异步编程。 |
| **mineru** | `>=2.5.0` | **核心引擎**：MinerU 核心库，提供 PDF 解析、布局分析和公式提取能力。 |
| **celery** | `>=5.5.3` | **异步任务队列**：用于处理耗时的 PDF 解析和 NLP任务。 |
| **vllm** | `>=0.11.0` | **大模型推理**：高性能 LLM/VLM 推理引擎，用于加速VLM视觉大模型的推理。 |
| **transformers** | `>=4.53.0` | **NLP 模型库**：用于加载和运行各种预训练模型（如 NER、Embedding）。 |
| **minio** | `>=7.2.15` | **对象存储客户端**：用于上传和下载 PDF 源文件及解析后的结果文件。 |
| **sentence-transformers** | `>=5.1.0` | **文本向量化**：用于生成文本 Embedding，实现基于文本语义的切分。 |
| **sqlalchemy** | `>=2.0.41` | **ORM 框架**：用于数据库操作 and 连接管理。 |
| **redis** | (Implied) | **缓存与消息中间件**：作为 Celery 的 Broker 和应用缓存（通过 `redislite` 或外部服务）。 |

## 应用价值

- **提质**：将非结构化文档转化为高质量的 Markdown 数据，为大模型知识库建设提供了坚实的基础。
- **增效**：通过自动化、并行化的处理流程，结合软件架构的优化，将文档处理效率提升数倍，实现了从“小时级”到“分钟级”的跨越。
- **赋能**：该平台可广泛应用于政策文件检索、合同智能审核、技术文档问答等多种业务场景，切实助力企业提效减负。

| 对比维度 | 原生 MinerU | 本方案 | 优势 |
| --- | --- | --- | --- |
| **系统架构** | 单体应用，命令行工具 | 分布式微服务架构（FastAPI + Celery + vLLM + Redis） | 支持高并发、可水平扩展，适合企业级部署 |
| **服务化能力** | 无服务接口，需本地调用 | 提供 RESTful API，支持 HTTP 调用 | 易于集成到现有系统，支持多语言调用 |
| **并发处理** | 单任务串行处理 | 分布式任务队列，支持多 Worker 并行 | 处理效率提升数倍，支持海量文档批量处理 |
| **资源利用** | CPU/GPU 资源利用率低 | CPU 密集任务与 GPU 推理任务分离，多卡并行 | 单机吞吐量大幅提升，资源利用最大化 |
| **文档格式支持** | 主要支持 PDF | 全格式支持（Word、Excel、PDF、PPT、图片） | 一站式解决企业多格式文档处理需求 |
| **表格处理** | 基础表格识别 | 智能表格处理（键值对转换 + Markdown 表格） | 满足问答 and 可视化展示双重场景需求 |
| **文本切分** | 无切分功能 | 基于语义的智能切分（BGE Embedding + 聚类） | 保证语义完整性，提升检索准确性 |
| **上下文管理** | 无标题聚合功能 | 上下文感知的标题聚合（多级标题路径保留） | 解决碎片化导致的上下文丢失问题 |
| **信息提取** | 无实体识别功能 | 集成 NER 模型，自动提取关键实体 | 支持多维度精准检索，为文档打智能标签 |

"""
def test_semantic_chunking_basic(embed_fn, sample_markdown):
    """测试基本的语义切分逻辑 (使用真实嵌入模型)"""

    # 配置切分参数
    parser_config = {
        "chunk_token_num": 1000,  # 针对标准文档调整 token 数
        "overlapped_percent": 0.1
    }

    # 执行语义切分
    chunks = semantic.chunk_markdown(
        sample_markdown,
        parser_config=parser_config,
        embed_fn=embed_fn
    )

    # 1. 基础验证
    assert isinstance(chunks, list)
    assert len(chunks) >= 5, f"预期至少切分为 5 个片段，实际仅有 {len(chunks)} 个"

    # 2. 验证上下文感知与标题聚合 (检查 RAGFlow 风格的层级路径)
    # 验证子章节片段是否保留了父级标题路径
    # 检查 "Docling" 相关的片段 (属于 "核心技术亮点" -> "多模态融合的高精度解析")
    docling_chunks = [c for c in chunks if "Docling" in c]
    assert docling_chunks, "未找到包含 'Docling' 的片段"
    for chunk in docling_chunks:
        assert "核心技术亮点" in chunk, "子章节片段丢失了父级标题 '核心技术亮点'"
        assert "多模态融合的高精度解析" in chunk, "子章节片段丢失了自身标题 '多模态融合的高精度解析'"
        # 验证层级分隔符
        path_part = chunk.split("\n")[0] if "\n" in chunk else chunk
        assert "|" in path_part, f"标题路径中缺失层级分隔符 '|': {path_part}"
        assert path_part.count("|") >= 1, f"标题路径层级深度不足: {path_part}"

    # 检查顶级章节 (Level 2) 是否保持独立 (不应包含其他不相关的顶级标题)
    pain_point_chunks = [c for c in chunks if "格式繁杂兼容难" in c]
    for chunk in pain_point_chunks:
        path_part = chunk.split("\n")[0]
        assert "痛点与挑战" in path_part
        assert "技术方案概览" not in path_part, "顶级标题路径污染：包含了不相关的顶级标题"

    # 3. 验证关键技术词汇识别
    # 重点检查文档中出现的核心组件词汇
    keywords_to_check = ["FastAPI", "Celery", "vLLM", "MinerU"]
    found_keywords = [s for s in keywords_to_check if any(s in chunk for chunk in chunks)]
    assert len(found_keywords) > 0, f"在切分结果中未找到关键技术词汇: {keywords_to_check}"

    # 4. 验证核心章节内容是否存在
    has_arch_section = any("架构设计" in chunk for chunk in chunks)
    has_highlight_section = any("核心技术亮点" in chunk for chunk in chunks)
    assert has_arch_section, "未找到 '架构设计' 相关内容"
    assert has_highlight_section, "未找到 '核心技术亮点' 相关内容"

    # 5. 验证语义聚类是否将不同主题分开
    # 架构设计和核心技术亮点是两个独立的大章节，语义聚类应该尽量避免将它们的核心内容混在一个 chunk 中
    arch_start_chunks = [i for i, c in enumerate(chunks) if "## 架构设计" in c]
    highlight_start_chunks = [i for i, c in enumerate(chunks) if "## 核心技术亮点" in c]

    if arch_start_chunks and highlight_start_chunks:
        # 确保起始片段不重合
        assert not set(arch_start_chunks).intersection(set(highlight_start_chunks)), \
            "语义聚类错误：架构设计与核心技术亮点的章节头部被挤在了同一个 chunk 中"

    print(f"\n[测试成功] 文档成功切分为 {len(chunks)} 个片段")
    print(f"识别到的关键技术词汇: {found_keywords}")

    # 直接输出到控制台预览切分结果，避免文件副作用
    print("\n--- 语义切分结果开始 ---")
    for idx, chunk in enumerate(chunks, 1):
        print(f"\n[Chunk {idx}]\n{chunk}")
    print("\n--- 语义切分结果结束 ---")
   
def test_heading_inference():
    """测试标题层级推断工具类"""
    from yuxi.knowledge.chunking.ragflow_like.utils.md_parser_utils import infer_heading_level
    
    assert infer_heading_level("1. 简介") == 1
    assert infer_heading_level("1.1 详细设计") == 2
    assert infer_heading_level("1.2.3 核心逻辑") == 3
    assert infer_heading_level("一、 背景") == 1
    assert infer_heading_level("普通文本") == 1