from __future__ import annotations

import pytest


from yuxi.modules.knowledge.graphs.extractors import normalize_extraction_result
from yuxi.modules.knowledge.graphs.extractors.base import (
    MAX_ENTITY_LABEL_LENGTH,
    MAX_ENTITY_NAME_LENGTH,
    MAX_RELATION_TYPE_LENGTH,
)
from yuxi.modules.knowledge.models import KnowledgeGraphEntity, KnowledgeGraphTriple

pytestmark = pytest.mark.usefixtures("milvus_graph_projection_lock")

# 真实案例形状：模型把摘要正文当成实体，长度超过数据库列上限。
ABSTRACT_PARAGRAPH = (
    "Reliable engine-weight estimation at the conceptual design stage is critical to the "
    "development of new aircraft engines. It helps to identify the best engine concept "
    "amongst several candidates. "
) * 6


def test_normalize_extraction_result_defaults_and_validates_refs():
    result = normalize_extraction_result(
        {
            "entities": [{"text": "张三"}, {"text": "公司"}],
            "relations": [{"source": "张三", "target": "公司", "text": "任职于"}],
        },
        "llm",
    )

    assert result["entities"][0]["label"] == "Entity"
    assert result["relations"][0]["label"] == "RELATED_TO"
    assert result["relations"][0]["source"] == {"text": "张三", "label": "Entity", "attributes": []}
    assert result["metadata"] == {"extractor_type": "llm", "schema_version": 1}


def test_normalize_extraction_result_accepts_llm_nested_relation_entities():
    result = normalize_extraction_result(
        {
            "relations": [
                {
                    "source": {
                        "text": "张三",
                        "label": "Person",
                        "attributes": [{"text": "工程师", "label": "Occupation"}],
                    },
                    "target": {"text": "公司", "label": "Organization"},
                    "text": "任职于",
                    "label": "WORKS_AT",
                }
            ]
        },
        "llm",
    )

    assert result["entities"] == [
        {"text": "张三", "label": "Person", "attributes": [{"text": "工程师", "label": "Occupation"}]},
        {"text": "公司", "label": "Organization", "attributes": []},
    ]
    assert result["relations"][0]["source"]["attributes"] == [{"text": "工程师", "label": "Occupation"}]
    assert result["relations"][0]["target"] == {"text": "公司", "label": "Organization", "attributes": []}


def test_normalize_extraction_result_drops_over_long_entity_and_its_relations():
    """超长实体必须被丢弃，而不是让同一批的好实体一起陪葬。

    原来做不到这一点：upsert_chunk_graph 把一个分块的所有实体放进一条多行 INSERT，
    一个值超过列长度，整批被 PostgreSQL 拒绝，该分块的图谱全部丢失且永远停在 pending。
    """
    result = normalize_extraction_result(
        {
            "entities": [
                {"text": "WATE", "label": "Tool"},
                {"text": ABSTRACT_PARAGRAPH, "label": "Abstract"},
                {"text": "NASA", "label": "Organization"},
            ],
            "relations": [
                {"source": "WATE", "target": "NASA", "text": "由...开发", "label": "DEVELOPED_BY"},
                {"source": "WATE", "target": ABSTRACT_PARAGRAPH, "text": "has abstract"},
            ],
        },
        "llm",
    )

    assert [entity["text"] for entity in result["entities"]] == ["WATE", "NASA"]
    assert [(relation["source"]["text"], relation["target"]["text"]) for relation in result["relations"]] == [("WATE", "NASA")]
    assert result["metadata"]["dropped_entities"] == 1
    assert result["metadata"]["dropped_relations"] == 1


def test_normalize_extraction_result_drops_over_long_inline_endpoint():
    """关系以内联对象给出实体时，只丢这一条关系，其余照常。"""
    result = normalize_extraction_result(
        {
            "relations": [
                {
                    "source": {"text": "WATE", "label": "Tool"},
                    "target": {"text": ABSTRACT_PARAGRAPH, "label": "Abstract"},
                    "text": "has abstract",
                },
                {
                    "source": {"text": "WATE", "label": "Tool"},
                    "target": {"text": "NASA", "label": "Organization"},
                    "text": "由...开发",
                },
            ]
        },
        "llm",
    )

    assert [entity["text"] for entity in result["entities"]] == ["WATE", "NASA"]
    assert len(result["relations"]) == 1
    assert result["metadata"]["dropped_relations"] == 1


def test_normalize_extraction_result_drops_over_long_label_and_relation_type():
    over_long_label = normalize_extraction_result(
        {"entities": [{"text": "WATE", "label": "X" * (MAX_ENTITY_LABEL_LENGTH + 1)}], "relations": []},
        "llm",
    )
    assert over_long_label["entities"] == []

    over_long_relation_type = normalize_extraction_result(
        {
            "entities": [{"text": "A"}, {"text": "B"}],
            "relations": [{"source": "A", "target": "B", "text": "r", "label": "T" * (MAX_RELATION_TYPE_LENGTH + 1)}],
        },
        "llm",
    )
    assert [entity["text"] for entity in over_long_relation_type["entities"]] == ["A", "B"]
    assert over_long_relation_type["relations"] == []


def test_normalize_extraction_result_always_fits_entity_columns():
    """不变量：规范化后的实体名不会再超过列长度——写入失败的根因就是这个。"""
    result = normalize_extraction_result(
        {"entities": [{"text": ABSTRACT_PARAGRAPH}, {"text": "长" * 600}, {"text": "ok"}], "relations": []},
        "llm",
    )

    assert [entity["text"] for entity in result["entities"]] == ["ok"]
    assert all(len(entity["text"]) <= MAX_ENTITY_NAME_LENGTH for entity in result["entities"])


def test_normalize_extraction_result_counts_dropped_entities_distinctly():
    """同一个越界实体被多条关系引用时，实体数按去重计，关系数按条计。"""
    result = normalize_extraction_result(
        {
            "entities": [{"text": "A"}, {"text": "B"}, {"text": ABSTRACT_PARAGRAPH}],
            "relations": [
                {"source": "A", "target": ABSTRACT_PARAGRAPH, "text": "r1"},
                {"source": "B", "target": ABSTRACT_PARAGRAPH, "text": "r2"},
            ],
        },
        "llm",
    )

    assert [entity["text"] for entity in result["entities"]] == ["A", "B"]
    assert result["relations"] == []
    assert result["metadata"]["dropped_entities"] == 1
    assert result["metadata"]["dropped_relations"] == 2


def test_normalize_extraction_result_drops_relation_with_over_long_ref():
    """关系只以裸字符串引用一个超长名（未出现在 entities[]）时，丢弃该关系而不是让整块失败。"""
    result = normalize_extraction_result(
        {
            "entities": [{"text": "A"}],
            "relations": [{"source": "A", "target": ABSTRACT_PARAGRAPH, "text": "r"}],
        },
        "llm",
    )

    assert [entity["text"] for entity in result["entities"]] == ["A"]
    assert result["relations"] == []
    assert result["metadata"]["dropped_relations"] == 1


def test_normalize_extraction_result_keeps_metadata_clean_without_drops():
    """没有丢弃时不写这两个键，避免改变既有产物的形状。"""
    result = normalize_extraction_result({"entities": [{"text": "A"}], "relations": []}, "llm")

    assert result["metadata"] == {"extractor_type": "llm", "schema_version": 1}


def test_normalize_extraction_result_still_rejects_unknown_ref():
    """丢弃只针对越界实体；引用一个从未出现过的实体仍然是错误，不能被一并静默吞掉。"""
    with pytest.raises(ValueError, match="未找到"):
        normalize_extraction_result(
            {"entities": [{"text": "A"}], "relations": [{"source": "A", "target": "不存在", "text": "r"}]},
            "llm",
        )


def test_normalizer_limits_match_graph_column_lengths():
    """守卫常量必须与列定义一致：列更短则守卫失效，列更长则白丢数据。"""
    assert MAX_ENTITY_NAME_LENGTH == KnowledgeGraphEntity.name.type.length
    assert MAX_ENTITY_NAME_LENGTH == KnowledgeGraphEntity.normalized_name.type.length
    assert MAX_ENTITY_LABEL_LENGTH == KnowledgeGraphEntity.label.type.length
    assert MAX_RELATION_TYPE_LENGTH == KnowledgeGraphTriple.relation_type.type.length


@pytest.mark.parametrize(
    "payload",
    [
        {"entities": [{"text": "张三"}], "relations": [{"source": "张三", "target": "不存在", "text": "关系"}]},
        {"entities": [{"text": ""}], "relations": []},
    ],
)
def test_normalize_extraction_result_rejects_invalid_payload(payload):
    with pytest.raises(ValueError):
        normalize_extraction_result(payload, "llm")


def test_normalized_relations_deduplicate_only_same_direction_and_label():
    """实体别名合并属性，重复关系去重，反向和不同类型保持独立。"""
    from yuxi.modules.knowledge.graphs.graph_utils import build_graph_payload

    result = normalize_extraction_result(
        {
            "entities": [
                {"text": "Alpha", "attributes": [{"text": "one", "label": "tag"}]},
                {"text": " ALPHA ", "attributes": [{"text": "two", "label": "tag"}]},
                {"text": "Beta"},
            ],
            "relations": [
                {"source": "Alpha", "target": "Beta", "label": "LINKS", "text": "first"},
                {"source": " ALPHA ", "target": "Beta", "label": "LINKS", "text": "duplicate"},
                {"source": "Beta", "target": "Alpha", "label": "LINKS", "text": "reverse"},
                {"source": "Alpha", "target": "Beta", "label": "KNOWS", "text": "different"},
            ],
        },
        "llm",
    )
    payload = build_graph_payload(result)
    assert [(e["id"], e["text"]) for e in payload["entities"]] == [("e1", "Alpha"), ("e2", "Beta")]
    assert payload["entities"][0]["attributes"] == [{"text": "one", "label": "tag"}, {"text": "two", "label": "tag"}]
    assert [(r["source"], r["target"], r["label"], r["text"]) for r in payload["relations"]] == [
        ("e1", "e2", "LINKS", "first"),
        ("e2", "e1", "LINKS", "reverse"),
        ("e1", "e2", "KNOWS", "different"),
    ]
