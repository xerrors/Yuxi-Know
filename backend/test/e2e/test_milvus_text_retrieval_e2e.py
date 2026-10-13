"""真实 worker、PostgreSQL、MinIO 与 Milvus 3 的检索闭环。"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock
from uuid import uuid4

import pymilvus
import pytest
from packaging.version import Version
from pymilvus import Collection, connections, utility
from sqlalchemy import select

from test.e2e.e2e_helpers import wait_model_provider_cache
from yuxi.bootstrap.models import load_models
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.knowledge.graphs.extractors import normalize_extraction_result
from yuxi.modules.knowledge.graphs.graph_utils import graph_entity_collection_name, graph_triple_collection_name
from yuxi.modules.knowledge.graphs.service import KnowledgeGraphService
from yuxi.modules.knowledge.graphs.milvus_graph_vector_store import MilvusGraphVectorStore
from yuxi.modules.knowledge.models import KnowledgeProjectionOutbox
from yuxi.modules.knowledge.repositories.chunks import KnowledgeChunkRepository
from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository
from yuxi.modules.knowledge.repositories.graphs import KnowledgeGraphRepository
from yuxi.modules.knowledge.repositories.projections import knowledge_projection_lock

load_models()
pytestmark = [pytest.mark.asyncio, pytest.mark.e2e]


async def _wait_job(client, headers, job_id):
    """等待真实 worker 的任务终态，失败直接暴露持久结果。"""
    async with asyncio.timeout(120):
        while True:
            response = await client.get(f"/api/background-jobs/{job_id}", headers=headers)
            assert response.status_code == 200, response.text
            job = response.json()["job"]
            if job["status"] in {"success", "failed", "cancelled"}:
                assert job["status"] == "success", job
                return
            await asyncio.sleep(0.2)


async def _wait_projection_cleanup(kb_id):
    """等待真实 worker 清理意图完成；随后仍需回读外部存储证明结果。"""
    async with asyncio.timeout(120):
        while True:
            async with pg_manager.get_async_session_context() as session:
                pending = await session.scalar(
                    select(KnowledgeProjectionOutbox.id)
                    .where(
                        KnowledgeProjectionOutbox.kb_id == kb_id,
                        KnowledgeProjectionOutbox.status != "applied",
                    )
                    .limit(1)
                )
            if pending is None:
                return
            await asyncio.sleep(0.2)


async def test_worker_index_and_all_search_modes_use_text_constraints(e2e_client, e2e_headers, monkeypatch):
    """索引后回读正文，验证三通道、中文、短语、高亮、重建和删除。"""

    class EmbeddingReplay(BaseHTTPRequestHandler):
        """提供固定四维向量，让文本约束拥有独立的检索 oracle。"""

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            inputs = payload["input"]
            if isinstance(inputs, str):
                inputs = [inputs]
            body = json.dumps(
                {
                    "object": "list",
                    "data": [{"object": "embedding", "index": i, "embedding": [1, 0, 0, 0]} for i in range(len(inputs))],
                    "model": "replay-embedding",
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    replay = ThreadingHTTPServer(("0.0.0.0", 0), EmbeddingReplay)
    thread = threading.Thread(target=replay.serve_forever, daemon=True)
    thread.start()
    provider_id = f"ci-milvus-{uuid4().hex[:8]}"
    kb_id = None
    provider_created = False
    alias = provider_id
    pg_manager.initialize()
    try:
        created = await e2e_client.post(
            "/api/system/model-providers",
            headers=e2e_headers,
            json={
                "provider_id": provider_id,
                "display_name": "Milvus E2E embedding",
                "provider_type": "openai",
                "base_url": f"http://api:{replay.server_port}/v1",
                "embedding_base_url": f"http://api:{replay.server_port}/v1/embeddings",
                "api_key": "ci-replay-key",
                "capabilities": ["embedding"],
                "is_enabled": True,
                "enabled_models": [{"id": "replay-embedding", "display_name": "Replay embedding", "type": "embedding", "dimension": 4}],
            },
        )
        assert created.status_code == 200, created.text
        provider_created = True
        await wait_model_provider_cache()
        created = await e2e_client.post(
            "/api/knowledge/knowledge-bases",
            headers=e2e_headers,
            json={
                "name": f"pytest_milvus3_{uuid4().hex}",
                "description": "Milvus text E2E",
                "kb_type": "milvus",
                "embedding_model_spec": f"{provider_id}:replay-embedding",
                "additional_params": {},
            },
        )
        assert created.status_code == 200, created.text
        kb_id = created.json()["kb_id"]
        samples = {
            "match.md": "Milvus vector database production reference.",
            "reversed.md": "Milvus database vector production reference.",
            "excluded.md": "Milvus vector database legacy reference.",
            "unrelated.md": "PostgreSQL transactional\nstorage reference.",
            "chinese.md": "知识库支持关键词检索以及混合检索。",
        }
        expected_lines = {name: (1, 2) if name == "unrelated.md" else (1, 1) for name in samples}
        file_ids = {}
        for name, text in samples.items():
            uploaded = await e2e_client.post(
                f"/api/knowledge/files/upload?kb_id={kb_id}",
                headers=e2e_headers,
                files={"file": (name, text.encode(), "text/markdown")},
            )
            assert uploaded.status_code == 200, uploaded.text
            info = uploaded.json()
            added = await e2e_client.post(
                f"/api/knowledge/knowledge-bases/{kb_id}/documents/add",
                headers=e2e_headers,
                json={
                    "items": [info["file_path"]],
                    "params": {
                        "content_hashes": {info["file_path"]: info["content_hash"]},
                        "file_sizes": {info["file_path"]: info["size"]},
                    },
                },
            )
            assert added.status_code == 200, added.text
            file_ids[name] = added.json()["items"][0]["file_id"]

        async def index_documents():
            """通过公共入口触发索引并等待 owning worker 的终态。"""
            indexed = await e2e_client.post(
                f"/api/knowledge/knowledge-bases/{kb_id}/documents/index",
                headers=e2e_headers,
                json={"file_ids": list(file_ids.values()), "params": {}},
            )
            assert indexed.status_code == 200, indexed.text
            await _wait_job(e2e_client, e2e_headers, indexed.json()["job_id"])

        parsed = await e2e_client.post(
            f"/api/knowledge/knowledge-bases/{kb_id}/documents/parse",
            headers=e2e_headers,
            json={"file_ids": list(file_ids.values()), "params": {}},
        )
        assert parsed.status_code == 200, parsed.text
        await _wait_job(e2e_client, e2e_headers, parsed.json()["job_id"])
        await index_documents()
        repository = KnowledgeChunkRepository()
        for name, file_id in file_ids.items():
            record = await KnowledgeFileRepository().get_by_file_id(file_id)
            assert record.status == "indexed", (name, record.status)
            [chunk] = await repository.list_by_file_id(file_id)
            assert chunk.content == samples[name]
            assert (chunk.start_line, chunk.end_line) == expected_lines[name]
            content_response = await e2e_client.get(
                f"/api/knowledge/knowledge-bases/{kb_id}/documents/{file_id}/content",
                headers=e2e_headers,
            )
            assert content_response.status_code == 200, content_response.text
            [preview_chunk] = content_response.json()["lines"]
            assert (preview_chunk["start_line"], preview_chunk["end_line"]) == expected_lines[name]
            assert content_response.json()["line_location"] == {"available": True, "reason": None}
            assert content_response.json()["content"] == samples[name]
        connections.connect(
            alias=alias,
            uri=os.environ["MILVUS_URI"],
            token=os.getenv("MILVUS_TOKEN", ""),
            db_name=os.getenv("MILVUS_DB", "yuxi"),
        )
        collection = Collection(kb_id, using=alias)
        assert Version(pymilvus.__version__) >= Version("3.0.2")
        assert Version(utility.get_server_version(using=alias)) >= Version("3.0.2")
        collection.load()
        stored = collection.query(expr='id != ""', output_fields=["content", "file_id"], consistency_level="Strong")
        assert {row["content"] for row in stored} == set(samples.values())

        graph_store = MilvusGraphVectorStore()
        for record_type, records in (
            ("entity", [{"id": "e1", "content": "Milvus vector database"}]),
            ("triple", [{"id": "t1", "content": "Milvus supports retrieval", "source_id": "e1", "target_id": "e2"}]),
        ):
            await graph_store.upsert_graph_records(
                kb_id=kb_id,
                embedding_model_spec=f"{provider_id}:replay-embedding",
                record_type=record_type,
                records=records,
            )
        [entity] = await graph_store.search_entities(
            kb_id=kb_id,
            query_text="Milvus",
            embedding_model_spec=f"{provider_id}:replay-embedding",
            top_k=10,
        )
        [triple] = await graph_store.search_triples(
            kb_id=kb_id,
            query_text="Milvus",
            embedding_model_spec=f"{provider_id}:replay-embedding",
            top_k=10,
        )
        assert entity["id"] == "e1" and entity["content"] == "Milvus vector database"
        assert triple["id"] == "t1" and triple["source_id"] == "e1" and triple["target_id"] == "e2"
        assert all(
            utility.has_collection(name, using=alias)
            for name in (
                graph_entity_collection_name(kb_id),
                graph_triple_collection_name(kb_id),
            )
        )

        async def query(mode, **options):
            """从 HTTP 返回读取真实服务端检索结果。"""
            response = await e2e_client.post(
                f"/api/knowledge/knowledge-bases/{kb_id}/query-test",
                headers=e2e_headers,
                json={
                    "query": options.pop("query", "Milvus"),
                    "meta": {
                        "search_mode": mode,
                        "final_top_k": 10,
                        "similarity_threshold": 0,
                        "use_reranker": False,
                        "use_graph_retrieval": False,
                        **options,
                    },
                },
            )
            assert response.status_code == 200, response.text
            results = response.json()
            expected_by_file = {file_ids[name]: lines for name, lines in expected_lines.items()}
            assert all(
                (row["metadata"]["start_line"], row["metadata"]["end_line"]) == expected_by_file[row["metadata"]["file_id"]]
                for row in results
            )
            return results

        active_entities = collection.query(
            expr='id != ""',
            output_fields=["id", "chunk_id", "file_id", "generation", "chunk_index", "content", "embedding"],
            consistency_level="Strong",
        )
        building_entities = [
            {
                **row,
                "id": row["id"] + "-building",
                "chunk_id": row["chunk_id"] + "-building",
                "generation": row["generation"] + 1000,
                "content": "Milvus",
                "embedding": [1, 0, 0, 0],
            }
            for row in active_entities
        ]
        try:
            # 非 active 候选在向量和 BM25 通道都更相关，必须在 top-k 截断前排除。
            collection.upsert([{**row, "embedding": [0, 1, 0, 0]} for row in active_entities] + building_entities)
            collection.flush()
            [raw_hits] = collection.search(
                data=[[1, 0, 0, 0]],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"nprobe": 10}},
                limit=1,
                output_fields=["generation"],
                consistency_level="Strong",
            )
            assert raw_hits[0].entity.get("generation") >= 1000
            for mode in ("vector", "keyword", "hybrid"):
                results = await query(mode, final_top_k=1, recall_top_k=1, bm25_top_k=1)
                assert len(results) == 1, "非 active 候选不能挤掉有效 top-k"
                [visible] = results
                assert not visible["metadata"]["chunk_id"].endswith("-building")
                assert visible["content"] in samples.values()
        finally:
            collection.delete(expr=f"id in {json.dumps([row['id'] for row in building_entities])}")
            collection.upsert(active_entities)
            collection.flush()

        assert len(await query("vector")) == 5
        for mode in ("vector", "keyword", "hybrid"):
            [result] = await query(mode, required_terms="Milvus", excluded_terms="legacy", exact_phrase="vector database")
            assert result["metadata"]["file_id"] == file_ids["match.md"]
            assert result["content"] == samples["match.md"]
            assert result["score_type"] == {"vector": "cosine", "keyword": "bm25", "hybrid": "hybrid"}[mode]
            assert any(segment["matched"] for fragment in result["highlights"] for segment in fragment)
            saved = await e2e_client.put(
                f"/api/knowledge/knowledge-bases/{kb_id}/query-params",
                headers=e2e_headers,
                json={
                    "search_mode": mode,
                    "required_terms": "Milvus",
                    "excluded_terms": "legacy",
                    "exact_phrase": "vector database",
                    "use_graph_retrieval": False,
                    "use_reranker": False,
                },
            )
            assert saved.status_code == 200, saved.text
            public = await e2e_client.post(
                "/api/v1/knowledge/tools/query_kb",
                headers=e2e_headers,
                json={"kb_id": kb_id, "query_text": "Milvus"},
            )
            assert public.status_code == 200, public.text
            [public_result] = public.json()["results"]
            restored = await e2e_client.put(
                f"/api/knowledge/knowledge-bases/{kb_id}/query-params",
                headers=e2e_headers,
                json={"search_mode": "vector", "required_terms": "", "excluded_terms": "", "exact_phrase": ""},
            )
            assert restored.status_code == 200, restored.text
            assert public_result["file_id"] == file_ids["match.md"]
            assert public_result["content"] == result["content"]
            assert public_result["metadata"]["score_type"] == result["score_type"]
            assert public_result["metadata"]["highlights"] == result["highlights"]
            assert await query(mode, file_name="unrelated", required_terms="Milvus") == []
            [by_file] = await query(mode, file_name="match.md")
            assert by_file["metadata"]["file_id"] == file_ids["match.md"]
        [chinese] = await query("keyword", query="关键词")
        assert chinese["content"] == samples["chinese.md"]
        assert any(segment["matched"] for fragment in chinese["highlights"] for segment in fragment)
        assert await query("keyword", exact_phrase='absent") or file_id != "') == []
        for result in await query("hybrid", highlight_results=False):
            assert "highlights" not in result
            assert result["content"] in samples.values()
        for options in ({"required_terms": ["bad"]}, {"search_mode": "unsupported"}):
            invalid = await e2e_client.post(
                f"/api/knowledge/knowledge-bases/{kb_id}/query-test",
                headers=e2e_headers,
                json={"query": "Milvus", "meta": options},
            )
            assert invalid.status_code == 400, invalid.text

        graph_repo = KnowledgeGraphRepository()
        graph_service = KnowledgeGraphService(graph_vector_store=graph_store)

        async def seed_file_graph(filename="match.md", attribute="public-A"):
            """为 active Chunk 发布真实 PG/Neo4j/图向量，验证代次与文件删除。"""
            [chunk] = await repository.list_by_file_id(file_ids[filename])
            payload = normalize_extraction_result(
                {
                    "entities": [
                        {"text": "Alpha", "attributes": [{"text": attribute}]},
                        {"text": "Beta"},
                        {"text": " ALPHA ", "attributes": [{"text": attribute}]},
                    ],
                    "relations": [
                        {"source": "Alpha", "target": "Beta", "text": "links"},
                        {"source": " ALPHA ", "target": "Beta", "text": "duplicate links"},
                    ],
                },
                "llm",
            )
            entities, triples = await asyncio.to_thread(graph_service.write_chunk_graph, kb_id, chunk, payload)
            await graph_repo.upsert_chunk_graph(
                kb_id=kb_id,
                file_id=chunk.file_id,
                chunk_id=chunk.chunk_id,
                entities=entities,
                triples=triples,
            )
            await repository.mark_graph_structure_indexed(chunk.chunk_id, ent_ids=[e["entity_id"] for e in entities])
            for kind in ("entity", "triple"):
                token, records = await graph_repo.claim_vector_records(
                    kb_id=kb_id,
                    record_type=kind,
                    limit=10,
                    lease_seconds=60,
                )
                if not records:
                    continue
                await graph_store.upsert_graph_records(
                    kb_id=kb_id,
                    embedding_model_spec=f"{provider_id}:replay-embedding",
                    record_type=kind,
                    records=records,
                )
                await graph_repo.mark_vector_records_indexed(
                    record_type=kind,
                    record_ids=[r["id"] for r in records],
                    lock_token=token,
                )
            for name, expected_ids in (
                (graph_entity_collection_name(kb_id), {e["entity_id"] for e in entities}),
                (graph_triple_collection_name(kb_id), {t["triple_id"] for t in triples}),
            ):
                projected = Collection(name, using=alias).query(expr='id != ""', output_fields=["id"], consistency_level="Strong")
                assert expected_ids <= {row["id"] for row in projected}
            assert await graph_repo.count_by_kb_id(kb_id) == (2, 1)

        def graph_node_count():
            """回读 Neo4j，而不是相信清理回调的返回值。"""
            with graph_service.driver.session() as session:
                return session.run("MATCH (n:MilvusKB {kb_id: $kb_id}) RETURN count(n) AS count", kb_id=kb_id).single()["count"]

        await seed_file_graph()
        assert await asyncio.to_thread(graph_node_count) == 3
        [seeded_chunk] = await repository.list_by_file_id(file_ids["match.md"])
        with monkeypatch.context() as scoped:
            scoped.setattr(graph_store, "delete_graph_records", AsyncMock(side_effect=RuntimeError("temporary cleanup failure")))
            with pytest.raises(RuntimeError, match="temporary cleanup failure"):
                await graph_service.delete_file_graph(kb_id, file_ids["match.md"], generation=seeded_chunk.generation)
        assert await graph_repo.count_by_kb_id(kb_id) == (2, 1)
        assert await asyncio.to_thread(graph_node_count) == 3
        await index_documents()
        assert len(await repository.list_by_kb_id(kb_id)) == 5
        await _wait_projection_cleanup(kb_id)
        assert await graph_repo.count_by_kb_id(kb_id) == (0, 0)
        assert await asyncio.to_thread(graph_node_count) == 0
        assert (
            len(
                await graph_store.search_entities(
                    kb_id=kb_id,
                    query_text="Milvus",
                    embedding_model_spec=f"{provider_id}:replay-embedding",
                    top_k=10,
                )
            )
            == 1
        )
        assert (
            len(
                await graph_store.search_triples(
                    kb_id=kb_id,
                    query_text="Milvus",
                    embedding_model_spec=f"{provider_id}:replay-embedding",
                    top_k=10,
                )
            )
            == 1
        )
        await seed_file_graph("chinese.md")
        await seed_file_graph("match.md", "PRIVATE_SOURCE_B")
        assert len(collection.query(expr='id != ""', output_fields=["file_id"], consistency_level="Strong")) == 5
        removed_file = file_ids["match.md"]
        before = await e2e_client.get("/api/graph/subgraph", headers=e2e_headers, params={"kb_id": kb_id})
        assert before.status_code == 200, before.text
        assert len(before.json()["data"]["nodes"]) == 4
        assert "PRIVATE_SOURCE_B" in json.dumps(before.json())
        async with knowledge_projection_lock(kb_id, shared=True):
            deleted = await e2e_client.delete(f"/api/knowledge/knowledge-bases/{kb_id}/documents/{removed_file}", headers=e2e_headers)
            assert deleted.status_code == 200, deleted.text
            assert await asyncio.to_thread(graph_node_count) == 4, "清理被锁阻塞，外部旧内容确实还在"
            hidden = await e2e_client.get("/api/graph/subgraph", headers=e2e_headers, params={"kb_id": kb_id})
            assert hidden.status_code == 200, hidden.text
            assert len(hidden.json()["data"]["nodes"]) == 3, "保留共享实体和可见文件的 Chunk"
            assert "PRIVATE_SOURCE_B" not in json.dumps(hidden.json()), "不可返回已删除来源的实体属性"
        assert await repository.list_by_file_id(removed_file) == []
        assert await KnowledgeFileRepository().get_by_file_id(removed_file) is None
        for mode in ("vector", "keyword", "hybrid"):
            assert all(result["metadata"]["file_id"] != removed_file for result in await query(mode))
        await _wait_projection_cleanup(kb_id)
        assert await graph_repo.count_by_kb_id(kb_id) == (2, 1)
        assert await asyncio.to_thread(graph_node_count) == 3
        shared = await e2e_client.get("/api/graph/subgraph", headers=e2e_headers, params={"kb_id": kb_id})
        assert len(shared.json()["data"]["nodes"]) == 3
        assert "PRIVATE_SOURCE_B" not in json.dumps(shared.json())
        assert collection.query(expr=f'file_id == "{removed_file}"', output_fields=["file_id"], consistency_level="Strong") == []
        deleted = await e2e_client.delete(f"/api/knowledge/knowledge-bases/{kb_id}", headers=e2e_headers)
        assert deleted.status_code == 200, deleted.text
        assert await repository.list_by_kb_id(kb_id) == []
        await _wait_projection_cleanup(kb_id)
        assert not utility.has_collection(kb_id, using=alias)
        assert not utility.has_collection(graph_entity_collection_name(kb_id), using=alias)
        assert not utility.has_collection(graph_triple_collection_name(kb_id), using=alias)
        assert await repository.list_by_kb_id(kb_id) == []
        kb_id = None
    finally:
        if kb_id:
            await e2e_client.delete(f"/api/knowledge/knowledge-bases/{kb_id}", headers=e2e_headers)
        if provider_created:
            await e2e_client.delete(f"/api/system/model-providers/{provider_id}", headers=e2e_headers)
        connections.disconnect(alias)
        await asyncio.to_thread(replay.shutdown)
        thread.join(timeout=5)
        replay.server_close()
        await pg_manager.close()
