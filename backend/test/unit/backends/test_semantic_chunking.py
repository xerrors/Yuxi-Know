import pytest
import numpy as np

# 现在可以安全地导入了，因为顶层不再有重型依赖
from yuxi.knowledge.chunking.ragflow_like.parsers import semantic

@pytest.fixture
def mock_embed_fn():
    """模拟一个简单的嵌入函数"""
    def encode(sentences):
        if isinstance(sentences, str):
            sentences = [sentences]
        # 返回模拟的向量 (N, 384)
        return np.random.rand(len(sentences), 384).astype(np.float32)
    return encode

@pytest.fixture
def sample_markdown():
    return """
# 核心业务说明

本节主要介绍公司的核心业务流程。

## 第一部分：研发流程
1. 需求分析：收集用户反馈。
2. 系统设计：架构方案评审。
3. 编码实现：遵循规范。

## 第二部分：交付标准
| 阶段 | 交付物 | 责任人 |
| --- | --- | --- |
| 交付1 | 源码包 | 开发 |
| 交付2 | 测试报告 | 测试 |

这里是一些额外的语义内容。
语义内容应当被聚类在一起。
这也是语义内容。
"""

def test_semantic_chunking_basic(mock_embed_fn, sample_markdown):
    """测试基本的语义切分逻辑 (使用注入方式)"""
    
    # 配置切分参数
    parser_config = {
        "chunk_token_num": 100,  # 触发语义切分
        "overlapped_percent": 0
    }
    
    # 直接注入 mock_embed_fn，完全跳过 config 加载
    chunks = semantic.chunk_markdown(
        sample_markdown, 
        parser_config=parser_config, 
        embed_fn=mock_embed_fn
    )
    
    # 验证结果
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    
    # 验证标题路径增强是否生效
    has_enhanced_title = any("# 核心业务说明|第一部分：研发流程" in chunk for chunk in chunks)
    assert has_enhanced_title, "标题路径增强失效"
    
    # 验证表格是否被正确保留
    has_table = any("交付1" in chunk and "源码包" in chunk for chunk in chunks)
    assert has_table, "表格内容丢失"
    
    print(f"\n成功切分为 {len(chunks)} 个片段")

def test_heading_inference():
    """测试标题层级推断工具类"""
    from yuxi.knowledge.chunking.ragflow_like.utils.md_parser_utils import infer_heading_level
    
    assert infer_heading_level("1. 简介") == 1
    assert infer_heading_level("1.1 详细设计") == 2
    assert infer_heading_level("1.2.3 核心逻辑") == 3
    assert infer_heading_level("一、 背景") == 1
    assert infer_heading_level("普通文本") == 1
