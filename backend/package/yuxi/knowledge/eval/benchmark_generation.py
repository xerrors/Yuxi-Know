import json
import math
import random
from collections.abc import AsyncIterator, Callable
from typing import Any

import json_repair

from yuxi import config
from yuxi.models import select_embedding_model, select_model
from yuxi.utils import logger


async def collect_kb_chunks(kb_instance: Any, db_id: str) -> list[dict[str, Any]]:
    chunks = []
    for fid, finfo in kb_instance.files_meta.items():
        if finfo.get("database_id") != db_id:
            continue
        try:
            content_info = await kb_instance.get_file_content(db_id, fid)
            for line in content_info.get("lines", []):
                chunks.append(
                    {
                        "id": line.get("id"),
                        "content": line.get("content", ""),
                        "file_id": fid,
                        "chunk_index": line.get("chunk_order_index"),
                    }
                )
        except Exception:
            continue
    return chunks


def clamp_neighbors_count(neighbors_count: int) -> int:
    return min(max(neighbors_count, 0), 10)


def cosine_similarity(a: list[float], b: list[float], na: float, nb: float) -> float:
    s = 0.0
    for i in range(len(a)):
        s += a[i] * b[i]
    return s / (na * nb)


def select_neighbor_indices(
    anchor_idx: int, embeddings: list[list[float]], norms: list[float], neighbors_count: int
) -> list[int]:
    anchor_embedding = embeddings[anchor_idx]
    anchor_norm = norms[anchor_idx]
    sims = []
    for idx in range(len(embeddings)):
        if idx == anchor_idx:
            continue
        score = cosine_similarity(anchor_embedding, embeddings[idx], anchor_norm, norms[idx])
        sims.append((idx, score))
    sims.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in sims[:neighbors_count]]


def build_benchmark_generation_prompt(ctx_items: list[tuple[str, str]]) -> str:
    context_text = "\n\n".join([f"片段ID={cid}\n{content}" for cid, content in ctx_items])
    return (
        "你将基于以下上下文生成一个可由上下文准确回答的问题与标准答案。"
        "仅返回一个JSON对象，不要包含其他文字。"
        "键为 query、gold_answer、gold_chunk_ids。gold_chunk_ids 必须是上述上下文片段的ID子集。\n\n"
        "上下文：\n" + context_text + "\n"
    )


async def iter_generated_benchmark_items(
    *,
    kb_instance: Any,
    db_id: str,
    count: int,
    neighbors_count: int,
    embedding_model_id: str,
    llm_model_spec: Any,
    progress_cb: Callable[[int, str], Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    if progress_cb:
        await progress_cb(5, "加载chunks")

    all_chunks = await collect_kb_chunks(kb_instance, db_id)
    if not all_chunks:
        raise ValueError("No chunks found in knowledge base")

    if progress_cb:
        await progress_cb(15, "向量化")

    contents = [chunk["content"] for chunk in all_chunks]
    embed_model = select_embedding_model(embedding_model_id)
    batch_size = int(getattr(embed_model, "batch_size", 40) or 40)
    if embedding_model_id in config.embed_model_names:
        batch_size = config.embed_model_names[embedding_model_id].batch_size

    embeddings = await embed_model.abatch_encode(contents, batch_size=batch_size)
    norms = [math.sqrt(sum(x * x for x in vec)) or 1.0 for vec in embeddings]
    llm = select_model(model_spec=llm_model_spec)
    neighbors_count = clamp_neighbors_count(neighbors_count)
    generated = 0
    attempts = 0
    max_attempts = max(count * 5, 50)

    if progress_cb:
        await progress_cb(0, "准备生成样本")

    while generated < count and attempts < max_attempts:
        attempts += 1
        anchor_idx = random.randrange(len(all_chunks))
        neighbor_indices = select_neighbor_indices(anchor_idx, embeddings, norms, neighbors_count)
        ctx_items = [(all_chunks[anchor_idx]["id"], all_chunks[anchor_idx]["content"])]
        ctx_items.extend((all_chunks[idx]["id"], all_chunks[idx]["content"]) for idx in neighbor_indices)
        allowed_ids = {cid for cid, _ in ctx_items}

        try:
            resp = await llm.call(build_benchmark_generation_prompt(ctx_items), False)
            obj = json_repair.loads(resp.content if resp else "")
            query = obj.get("query")
            answer = obj.get("gold_answer")
            gold_ids = obj.get("gold_chunk_ids")
            if not query or not answer or not isinstance(gold_ids, list):
                logger.warning(f"Generated JSON missing fields or invalid format: {obj}")
                continue

            gold_ids = [str(item) for item in gold_ids if str(item) in allowed_ids]
            if not gold_ids:
                logger.warning("Generated gold_chunk_ids not found in allowed context")
                continue

            generated += 1
            if progress_cb:
                await progress_cb(0 + int(99 * generated / max(count, 1)), f"已生成 {generated}/{count}")
            yield {"query": query, "gold_chunk_ids": gold_ids, "gold_answer": answer}
        except Exception as e:
            logger.warning(f"Benchmark generation failed for one item: {e}")
            continue


def dump_benchmark_item(item: dict[str, Any]) -> str:
    return json.dumps(item, ensure_ascii=False) + "\n"
