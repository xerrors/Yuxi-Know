import json
import random
from collections.abc import AsyncIterator, Callable
from typing import Any

import json_repair

from yuxi.models import select_model
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


def _is_anchor_chunk(candidate: dict[str, Any], anchor_chunk: dict[str, Any]) -> bool:
    metadata = candidate.get("metadata") or {}
    candidate_id = metadata.get("chunk_id")
    if candidate_id is not None and str(candidate_id) == str(anchor_chunk.get("id")):
        return True

    candidate_file_id = metadata.get("file_id")
    candidate_chunk_index = metadata.get("chunk_index")
    return candidate_file_id == anchor_chunk.get("file_id") and candidate_chunk_index == anchor_chunk.get("chunk_index")


async def select_neighbor_chunks_by_kb_query(
    *, kb_instance: Any, db_id: str, anchor_chunk: dict[str, Any], neighbors_count: int
) -> list[dict[str, Any]]:
    if neighbors_count <= 0:
        return []

    anchor_content = anchor_chunk.get("content", "")
    if not anchor_content:
        return []

    candidates = await kb_instance.aquery(
        anchor_content,
        db_id,
        search_mode="vector",
        final_top_k=neighbors_count + 3,
        use_reranker=False,
        similarity_threshold=0.0,
    )

    chunks = []
    for candidate in candidates:
        if _is_anchor_chunk(candidate, anchor_chunk):
            continue

        metadata = candidate.get("metadata") or {}
        chunk_id = metadata.get("chunk_id")
        content = candidate.get("content", "")
        if not chunk_id or not content:
            continue

        chunks.append(
            {
                "id": str(chunk_id),
                "content": content,
                "file_id": metadata.get("file_id"),
                "chunk_index": metadata.get("chunk_index"),
            }
        )
        if len(chunks) >= neighbors_count:
            break

    return chunks


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
    llm_model_spec: Any,
    progress_cb: Callable[[int, str], Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    if progress_cb:
        await progress_cb(5, "加载chunks")

    all_chunks = await collect_kb_chunks(kb_instance, db_id)
    if not all_chunks:
        raise ValueError("No chunks found in knowledge base")

    if progress_cb:
        await progress_cb(15, "准备生成样本")

    llm = select_model(model_spec=llm_model_spec)
    context_count = max(clamp_neighbors_count(neighbors_count), 1)
    generated = 0
    attempts = 0
    max_attempts = max(count * 5, 50)

    while generated < count and attempts < max_attempts:
        attempts += 1
        anchor_chunk = all_chunks[random.randrange(len(all_chunks))]
        neighbor_chunks = await select_neighbor_chunks_by_kb_query(
            kb_instance=kb_instance,
            db_id=db_id,
            anchor_chunk=anchor_chunk,
            neighbors_count=context_count - 1,
        )
        ctx_chunks = [anchor_chunk] + neighbor_chunks
        ctx_items = [(chunk["id"], chunk["content"]) for chunk in ctx_chunks]
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
