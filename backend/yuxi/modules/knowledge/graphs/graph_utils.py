"""图谱构建相关的纯函数工具集。

将数据变换逻辑从 KnowledgeGraphService 中抽离，
使 service 类专注于 I/O 和业务编排。
"""

from __future__ import annotations

from typing import Any

from yuxi.shared.hashing import hashstr


def normalize_entity_name(text: str) -> str:
    """统一实体名称：去首尾空白、小写化、压缩内部连续空白。"""
    return " ".join(text.strip().lower().split())


def compute_entity_id(kb_id: str, normalized_name: str, label: str) -> str:
    return hashstr(f"{kb_id}:{normalized_name}:{label}", length=32)


def compute_triple_id(
    kb_id: str,
    source_normalized_name: str,
    source_label: str,
    relation_type: str,
    target_normalized_name: str,
    target_label: str,
) -> str:
    return hashstr(
        f"{kb_id}:{source_normalized_name}:{source_label}:{relation_type}:{target_normalized_name}:{target_label}",
        length=32,
    )


def graph_entity_collection_name(kb_id: str) -> str:
    return f"{kb_id}_entity"


def graph_triple_collection_name(kb_id: str) -> str:
    return f"{kb_id}_triple"


def build_graph_payload(normalized_result: dict[str, Any]) -> dict[str, Any]:
    """将抽取器产出的标准化结果转换为 Neo4j 写入所需的图结构。

    输入经过 normalize_extraction_result；这里只分配局部 ID 并转换关系引用。
    """
    entities = [{**entity, "id": f"e{index}"} for index, entity in enumerate(normalized_result["entities"], 1)]
    entity_ids = {(normalize_entity_name(entity["text"]), entity["label"]): entity["id"] for entity in entities}
    relations = [
        {
            **relation,
            "source": entity_ids[(normalize_entity_name(relation["source"]["text"]), relation["source"]["label"])],
            "target": entity_ids[(normalize_entity_name(relation["target"]["text"]), relation["target"]["label"])],
        }
        for relation in normalized_result["relations"]
    ]
    return {"entities": entities, "relations": relations, "metadata": normalized_result["metadata"]}


# ─── Cypher 模板 ────────────────────────────────────────────────
# 将大段 Cypher 字符串集中管理，提升 write_chunk_graph 的可读性。


def cypher_merge_chunk(kb_label: str) -> str:
    """MERGE Chunk 节点并写入元数据。"""
    return f"""
    MERGE (c:Chunk:MilvusKB:`{kb_label}` {{chunk_id: $chunk_id}})
    SET c.file_id = $file_id,
        c.kb_id = $kb_id,
        c.chunk_index = $chunk_index,
        c.content_preview = $content_preview,
        c.start_char_pos = $start_char_pos,
        c.end_char_pos = $end_char_pos
    """


def cypher_merge_entity_mention(kb_label: str) -> str:
    """MERGE Entity 节点并创建 Chunk → Entity 的 MENTIONS 关系。"""
    return f"""
    MATCH (c:Chunk:MilvusKB:`{kb_label}` {{chunk_id: $chunk_id}})
    MERGE (e:Entity:MilvusKB:`{kb_label}` {{
        kb_id: $kb_id,
        normalized_name: $normalized_name,
        label: $entity_label
    }})
    SET e.entity_id = $entity_id,
        e.name = $name,
        e.attributes = $attributes,
        e.source_chunk_id = $chunk_id
    MERGE (c)-[m:MENTIONS {{chunk_id: $chunk_id, file_id: $file_id, kb_id: $kb_id}}]->(e)
    """


def cypher_merge_relation(kb_label: str) -> str:
    """MERGE 两个 Entity 之间的 RELATION 边。"""
    return f"""
    MATCH (source:Entity:MilvusKB:`{kb_label}` {{
        kb_id: $kb_id,
        normalized_name: $source_name,
        label: $source_label
    }})
    MATCH (target:Entity:MilvusKB:`{kb_label}` {{
        kb_id: $kb_id,
        normalized_name: $target_name,
        label: $target_label
    }})
    MERGE (source)-[r:RELATION {{
        kb_id: $kb_id,
        chunk_id: $chunk_id,
        source_name: $source_name,
        target_name: $target_name,
        type: $relation_type
    }}]->(target)
    SET r.triple_id = $triple_id,
        r.text = $text,
        r.file_id = $file_id,
        r.extractor_type = $extractor_type
    """
