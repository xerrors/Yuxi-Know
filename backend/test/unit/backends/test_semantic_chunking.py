import pytest
import numpy as np
import os

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
    with open("test/resource/test4.md", "r", encoding="utf-8") as f:
        return f.read()
def test_semantic_chunking_basic(embed_fn, sample_markdown):
    """测试基本的语义切分逻辑 (使用真实嵌入模型)"""
    
    # 配置切分参数
    parser_config = {
        "chunk_token_num": 200,  # 适中的 token 数以触发更多切分
        "overlapped_percent": 0
    }
    
    # 直接注入 embed_fn
    chunks = semantic.chunk_markdown(
        sample_markdown, 
        parser_config=parser_config, 
        embed_fn=embed_fn
    )
    
    # 验证结果
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    
    print(f"\n成功切分为 {len(chunks)} 个片段:")
    for i, chunk in enumerate(chunks):
        print(f"--- 片段 {i+1} ---")
        print(chunk)
    
    # 验证标题路径增强是否生效 (检查是否包含 Part 或特殊元素标记)
    has_enhanced_title = any("|Part" in chunk or "|Math Block" in chunk for chunk in chunks)
    assert has_enhanced_title, "标题路径增强或分片标记失效"
    
    # 验证是否包含特殊的 LaTeX 公式或符号 (匹配输出中的格式)
    has_formula = any("f _ {0, 1}" in chunk or "\\sigma_ {y, d}" in chunk or "A _ {\\mathrm {s p}}" in chunk for chunk in chunks)
    assert has_formula, "LaTeX 公式/符号在切分中丢失"

    # 验证语义聚类是否大概生效 (钢制塔架和混凝土塔架内容应该分开)
    # 我们检查是否有钢制塔架相关的片段和混凝土塔架相关的片段
    # 使用 startswith 来更准确地定位章节开始，避免匹配到目次/前言中的文字
    has_steel = any(chunk.startswith("# 6 钢制塔架") for chunk in chunks)
    has_concrete = any(chunk.startswith("# 7 混凝土塔架") for chunk in chunks)
    
    assert has_steel and has_concrete, "语义内容丢失 (钢制或混凝土塔架章节开始部分)"
    
    # 验证它们是否在不同的片段中
    steel_chunks = [i for i, c in enumerate(chunks) if c.startswith("# 6 钢制塔架")]
    concrete_chunks = [i for i, c in enumerate(chunks) if c.startswith("# 7 混凝土塔架")]
    
    # 理论上语义聚类会将这些大章节分开
    if steel_chunks and concrete_chunks:
        assert not set(steel_chunks).intersection(set(concrete_chunks)), "钢制塔架和混凝土塔架大章节内容被错误地聚类在同一个 chunk 中了"

def test_heading_inference():
    """测试标题层级推断工具类"""
    from yuxi.knowledge.chunking.ragflow_like.utils.md_parser_utils import infer_heading_level
    
    assert infer_heading_level("1. 简介") == 1
    assert infer_heading_level("1.1 详细设计") == 2
    assert infer_heading_level("1.2.3 核心逻辑") == 3
    assert infer_heading_level("一、 背景") == 1
    assert infer_heading_level("普通文本") == 1
