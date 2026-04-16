import pytest
import numpy as np
import os
import json

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
# 风力发电机组 塔架设计规范

## 1 概述
本标准规定了风力发电机组塔架的设计、制造、运输和安装要求。

## 6 钢制塔架
### 6.1 一般要求
钢制塔架的设计应考虑极端载荷和疲劳载荷。在计算连接强度时，需要用到螺纹截面积 Asp 以及承载力设计值 Rd。
此外，结构应力 σ _ {y, d} 的计算必须符合相关标准要求。

### 6.2 疲劳极限状态
疲劳计算应基于 Miner 线性累积损伤理论。

## 7 混凝土塔架
### 7.1 材料特性
混凝土强度等级不应低于 C50。

### 7.2 施工工艺
混凝土塔架可采用现浇或预制拼装方式。对于预制片段，应严格控制拼装精度。
"""
def test_semantic_chunking_basic(embed_fn, sample_markdown):
    """测试基本的语义切分逻辑 (使用真实嵌入模型)"""

    # 配置切分参数
    parser_config = {
        "chunk_token_num": 300,  # 针对标准文档调整 token 数
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

    # 2. 验证标题路径增强 (检查 RAGFlow 风格的层级标记)
    # 标准文档通常会被赋予类似 "风力发电机组 塔架 | 6 钢制塔架" 的标题路径
    has_enhanced_title = any("|" in chunk and ("钢制塔架" in chunk or "混凝土塔架" in chunk) for chunk in chunks)
    assert has_enhanced_title, "标题路径增强失效：未在 chunk 中发现层级分隔符 '|' 或核心章节标题"

    # 3. 验证公式与符号识别 (匹配 test4.md 4.1 节中的符号)
    # 重点检查文档中出现的符号：Asp (螺纹截面积), σ _ {y, d} (结构应力), Rd (承载力设计值)
    symbols_to_check = ["Asp", "Rd", "σ _ {y, d}"]
    found_symbols = [s for s in symbols_to_check if any(s in chunk for chunk in chunks)]
    assert len(found_symbols) > 0, f"在切分结果中未找到关键符号: {symbols_to_check}"

    # 4. 验证核心章节内容是否存在
    has_steel_section = any("6 钢制塔架" in chunk for chunk in chunks)
    has_concrete_section = any("7 混凝土塔架" in chunk for chunk in chunks)
    assert has_steel_section, "未找到第 6 章 '钢制塔架' 相关内容"
    assert has_concrete_section, "未找到第 7 章 '混凝土塔架' 相关内容"

    # 5. 验证语义聚类是否将不同主题分开
    # 钢制塔架和混凝土塔架是两个独立的大章节，语义聚类应该避免将它们的核心内容混在一个 chunk 中
    steel_start_chunks = [i for i, c in enumerate(chunks) if "# 6 钢制塔架" in c]
    concrete_start_chunks = [i for i, c in enumerate(chunks) if "# 7 混凝土塔架" in c]

    if steel_start_chunks and concrete_start_chunks:
        # 确保起始片段不重合
        assert not set(steel_start_chunks).intersection(set(concrete_start_chunks)), \
            "语义聚类错误：钢制塔架与混凝土塔架的章节头部被挤在了同一个 chunk 中"

    print(f"\n[测试成功] 文档成功切分为 {len(chunks)} 个片段")
    print(f"识别到的关键符号: {found_symbols}")

    # 将切分后的内容写入到 resource 目录
    output_dir = os.path.join(os.path.dirname(__file__), "resource")
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, "semantic_chunks.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"切分内容已保存至: {output_path}")
   
def test_heading_inference():
    """测试标题层级推断工具类"""
    from yuxi.knowledge.chunking.ragflow_like.utils.md_parser_utils import infer_heading_level
    
    assert infer_heading_level("1. 简介") == 1
    assert infer_heading_level("1.1 详细设计") == 2
    assert infer_heading_level("1.2.3 核心逻辑") == 3
    assert infer_heading_level("一、 背景") == 1
    assert infer_heading_level("普通文本") == 1
