from __future__ import annotations

import asyncio
import os
from typing import Any

from pymilvus import (
    Collection,
    DataType,
    FieldSchema,
    connections,
    db,
    utility,
)

from yuxi.infrastructure.filesystem import await_io
from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.knowledge.graphs.graph_utils import graph_entity_collection_name, graph_triple_collection_name
from yuxi.modules.knowledge.storage.milvus import (
    VECTOR_METRIC_TYPE,
    content_fields,
    embedding_field,
    create_collection,
    get_embedding_function,
)
from yuxi.modules.knowledge.storage.offload import run_milvus_query_io
from yuxi.modules.models.providers.cache import model_cache
from yuxi.shared.hashing import hashstr


class MilvusGraphVectorStore:
    def __init__(self):
        self.milvus_token = os.getenv("MILVUS_TOKEN") or ""
        self.milvus_uri = os.getenv("MILVUS_URI") or "http://localhost:19530"
        self.milvus_db = os.getenv("MILVUS_DB") or "yuxi"
        self.connection_alias = f"milvus_graph_{hashstr(self.milvus_uri, 6)}"
        self._init_connection()

    def _init_connection(self) -> None:
        if not connections.has_connection(self.connection_alias):
            connections.connect(alias=self.connection_alias, uri=self.milvus_uri, token=self.milvus_token)
        if self.milvus_db not in db.list_database(using=self.connection_alias):
            db.create_database(self.milvus_db, using=self.connection_alias)
        db.using_database(self.milvus_db, using=self.connection_alias)

    async def upsert_graph_records(
        self,
        *,
        kb_id: str,
        embedding_model_spec: str,
        record_type: str,
        records: list[dict[str, Any]],
    ) -> None:
        if not records:
            return
        embedding_info = model_cache.get_model_info(embedding_model_spec)
        if not embedding_info or embedding_info.model_type != "embedding":
            raise ValueError(f"Unsupported embedding model: {embedding_model_spec}")

        if record_type == "entity":
            collection = await await_io(asyncio.to_thread(self._get_or_create_entity_collection, kb_id, embedding_info))
        elif record_type == "triple":
            collection = await await_io(asyncio.to_thread(self._get_or_create_triple_collection, kb_id, embedding_info))
        else:
            raise ValueError(f"Unsupported graph vector record type: {record_type}")

        embed = get_embedding_function(embedding_model_spec)
        embeddings = await embed([record["content"] for record in records])
        if record_type == "entity":
            await await_io(asyncio.to_thread(self._upsert_entities, collection, records, embeddings))
        else:
            await await_io(asyncio.to_thread(self._upsert_triples, collection, records, embeddings))

    async def delete_graph_records(self, kb_id: str, *, entity_ids: list[str], triple_ids: list[str]) -> None:
        tasks = []
        if entity_ids:
            tasks.append(asyncio.to_thread(self._delete_ids, graph_entity_collection_name(kb_id), entity_ids))
        if triple_ids:
            tasks.append(asyncio.to_thread(self._delete_ids, graph_triple_collection_name(kb_id), triple_ids))
        if tasks:
            results = await await_io(asyncio.gather(*tasks, return_exceptions=True))
            for result in results:
                if isinstance(result, BaseException):
                    raise result

    async def search_entities(
        self,
        *,
        kb_id: str,
        query_text: str,
        embedding_model_spec: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        collection_name = graph_entity_collection_name(kb_id)
        has_collection = await run_milvus_query_io(utility.has_collection, collection_name, using=self.connection_alias)
        if not has_collection:
            return []
        return await self._search_graph_collection(
            collection_name=collection_name,
            query_text=query_text,
            embedding_model_spec=embedding_model_spec,
            top_k=top_k,
            output_fields=["id", "content"],
        )

    async def search_triples(
        self,
        *,
        kb_id: str,
        query_text: str,
        embedding_model_spec: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        collection_name = graph_triple_collection_name(kb_id)
        has_collection = await run_milvus_query_io(utility.has_collection, collection_name, using=self.connection_alias)
        if not has_collection:
            return []
        return await self._search_graph_collection(
            collection_name=collection_name,
            query_text=query_text,
            embedding_model_spec=embedding_model_spec,
            top_k=top_k,
            output_fields=["id", "content", "source_id", "target_id"],
        )

    def drop_graph_collections(self, kb_id: str) -> None:
        for collection_name in [graph_entity_collection_name(kb_id), graph_triple_collection_name(kb_id)]:
            try:
                if utility.has_collection(collection_name, using=self.connection_alias):
                    utility.drop_collection(collection_name, using=self.connection_alias)
                    logger.info(f"Dropped Milvus graph collection {collection_name}")
            except Exception as exc:
                logger.error(f"Failed to drop Milvus graph collection {collection_name}: {exc}")
                raise

    async def _search_graph_collection(
        self,
        *,
        collection_name: str,
        query_text: str,
        embedding_model_spec: str,
        top_k: int,
        output_fields: list[str],
    ) -> list[dict[str, Any]]:
        if top_k <= 0:
            return []
        embed = get_embedding_function(embedding_model_spec)
        query_embedding = await embed([query_text])
        return await run_milvus_query_io(
            self._search_graph_collection_sync,
            collection_name,
            query_embedding,
            max(top_k, 1),
            output_fields,
        )

    def _search_graph_collection_sync(
        self,
        collection_name: str,
        query_embedding: list,
        top_k: int,
        output_fields: list[str],
    ) -> list[dict[str, Any]]:
        collection = Collection(name=collection_name, using=self.connection_alias)
        collection.load()
        return self._search_loaded_collection(collection, query_embedding, top_k, output_fields)

    def _search_loaded_collection(
        self,
        collection: Collection,
        query_embedding: list,
        top_k: int,
        output_fields: list[str],
    ) -> list[dict[str, Any]]:
        results = collection.search(
            data=query_embedding,
            anns_field="embedding",
            param={"metric_type": VECTOR_METRIC_TYPE, "params": {"nprobe": 10}},
            limit=top_k,
            output_fields=output_fields,
        )
        if not results or not results[0]:
            return []

        records = []
        for hit in results[0]:
            entity = hit.entity
            record = {field: entity.get(field) for field in output_fields}
            record["score"] = float(hit.distance or 0.0)
            records.append(record)
        return records

    def _get_or_create_entity_collection(self, kb_id: str, embedding_info: Any) -> Collection:
        collection_name = graph_entity_collection_name(kb_id)
        fields = [*content_fields(), embedding_field(embedding_info.dimension or 1024)]
        return self._get_or_create_collection(collection_name, fields, embedding_info)

    def _get_or_create_triple_collection(self, kb_id: str, embedding_info: Any) -> Collection:
        collection_name = graph_triple_collection_name(kb_id)
        fields = [
            *content_fields(),
            FieldSchema(name="source_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="target_id", dtype=DataType.VARCHAR, max_length=100),
            embedding_field(embedding_info.dimension or 1024),
        ]
        return self._get_or_create_collection(collection_name, fields, embedding_info)

    def _get_or_create_collection(self, collection_name: str, fields: list[FieldSchema], embedding_info: Any) -> Collection:
        if utility.has_collection(collection_name, using=self.connection_alias):
            return Collection(name=collection_name, using=self.connection_alias)

        return create_collection(
            collection_name,
            fields=fields,
            description=f"Knowledge graph collection {collection_name} using {embedding_info.model_id}",
            using=self.connection_alias,
        )

    def _upsert_entities(self, collection: Collection, records: list[dict[str, Any]], embeddings: list) -> None:
        collection.upsert(
            [
                [record["id"] for record in records],
                [record["content"] for record in records],
                embeddings,
            ]
        )

    def _upsert_triples(self, collection: Collection, records: list[dict[str, Any]], embeddings: list) -> None:
        collection.upsert(
            [
                [record["id"] for record in records],
                [record["content"] for record in records],
                [record["source_id"] for record in records],
                [record["target_id"] for record in records],
                embeddings,
            ]
        )

    def _delete_ids(self, collection_name: str, ids: list[str]) -> None:
        if not utility.has_collection(collection_name, using=self.connection_alias):
            return
        collection = Collection(name=collection_name, using=self.connection_alias)
        for start in range(0, len(ids), 1000):
            batch = ids[start : start + 1000]
            quoted_ids = ", ".join(f'"{item}"' for item in batch)
            collection.delete(expr=f"id in [{quoted_ids}]")
