from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from yuxi.config import config
from yuxi.knowledge import knowledge_base
from yuxi.knowledge.utils.kb_utils import parse_minio_url
from yuxi.repositories.knowledge_file_repository import KnowledgeFileRepository
from yuxi.storage.minio import get_minio_client

KBS_PATH = "/home/gem/kbs"
PARSED_DIR_NAME = "parsed"
_INVALID_MOUNT_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MULTISPACE = re.compile(r"\s+")


def get_kb_cache_root() -> Path:
    return Path(config.save_dir) / "knowledge_base_data" / "kb-cache"


def normalize_knowledge_mount_name(name: str) -> str:
    normalized = _MULTISPACE.sub(" ", str(name or "").strip())
    if _INVALID_MOUNT_NAME_CHARS.search(normalized):
        raise ValueError("知识库名称包含不能映射为目录名的非法字符")
    normalized = normalized.strip(" .")
    if not normalized or normalized in {".", ".."}:
        raise ValueError("知识库名称不能映射为有效目录名")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("知识库名称不能包含路径分隔符")
    return normalized


def validate_knowledge_mount_name(name: str) -> str:
    return normalize_knowledge_mount_name(name)


def _normalize_selected_knowledges(selected: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in selected or []:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _derive_parsed_filename(filename: str, file_id: str, used_names: set[str]) -> str:
    raw_name = (filename or file_id or "file").strip() or file_id or "file"
    suffix = Path(raw_name).suffix
    stem = Path(raw_name).name[: -len(suffix)] if suffix else Path(raw_name).name
    candidate = f"{stem or file_id}.md"
    lowered = candidate.casefold()
    if lowered in used_names:
        candidate = f"{stem or file_id}__{file_id}.md"
        lowered = candidate.casefold()
    used_names.add(lowered)
    return candidate


def _serialize_file_record(record) -> dict[str, Any]:
    return {
        "file_id": record.file_id,
        "db_id": record.db_id,
        "parent_id": record.parent_id,
        "filename": record.filename,
        "original_filename": record.original_filename,
        "file_type": record.file_type,
        "path": record.path,
        "minio_url": record.minio_url,
        "markdown_file": record.markdown_file,
        "status": record.status,
        "content_hash": record.content_hash,
        "file_size": record.file_size,
        "content_type": record.content_type,
        "processing_params": record.processing_params,
        "is_folder": bool(record.is_folder),
    }


async def build_visible_knowledge_mounts(
    *,
    user_id: str,
    selected_knowledges: list[str] | None,
) -> list[dict[str, Any]]:
    accessible = (await knowledge_base.get_databases_by_user_id(user_id)).get("databases", [])
    selected = _normalize_selected_knowledges(selected_knowledges)
    selected_keys = {item.casefold() for item in selected}

    file_repo = KnowledgeFileRepository()
    mounts: list[dict[str, Any]] = []
    used_mount_names: dict[str, str] = {}

    for db in accessible:
        db_id = str(db.get("db_id") or "").strip()
        db_name = str(db.get("name") or db_id).strip()
        if not db_id or not db_name:
            continue
        if selected_keys and db_name.casefold() not in selected_keys and db_id.casefold() not in selected_keys:
            continue

        mount_name = normalize_knowledge_mount_name(db_name)
        conflict_db_id = used_mount_names.get(mount_name.casefold())
        if conflict_db_id and conflict_db_id != db_id:
            raise ValueError(f"知识库名称映射冲突: '{db_name}' -> '{mount_name}'")
        used_mount_names[mount_name.casefold()] = db_id

        records = await file_repo.list_by_db_id(db_id)
        mounts.append(
            {
                "db_id": db_id,
                "db_name": db_name,
                "mount_name": mount_name,
                "files": [_serialize_file_record(record) for record in records],
            }
        )

    mounts.sort(key=lambda item: item["mount_name"].casefold())
    return mounts


def cache_minio_object(*, source_url: str, metadata: dict[str, Any] | None = None) -> Path:
    bucket_name, object_name = parse_minio_url(source_url)
    minio_client = get_minio_client()
    stat = minio_client.client.stat_object(bucket_name=bucket_name, object_name=object_name)
    etag = str(getattr(stat, "etag", "") or "")
    last_modified = getattr(stat, "last_modified", None)
    version_key = etag or (last_modified.isoformat() if last_modified else "")
    cache_key = hashlib.sha256(f"{bucket_name}:{object_name}:{version_key}".encode()).hexdigest()

    suffix = Path(object_name).suffix
    objects_root = get_kb_cache_root() / "objects"
    manifests_root = get_kb_cache_root() / "manifests"
    objects_root.mkdir(parents=True, exist_ok=True)
    manifests_root.mkdir(parents=True, exist_ok=True)

    cached_path = objects_root / f"{cache_key}{suffix}"
    if not cached_path.exists():
        payload = minio_client.download_file(bucket_name=bucket_name, object_name=object_name)
        with tempfile.NamedTemporaryFile(dir=objects_root, delete=False) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        tmp_path.replace(cached_path)

    manifest_path = manifests_root / f"{cache_key}.json"
    if not manifest_path.exists():
        manifest = {
            "bucket_name": bucket_name,
            "object_name": object_name,
            "etag": etag,
            "last_modified": last_modified.isoformat() if last_modified else None,
            "source_url": source_url,
            "cached_path": str(cached_path),
            "metadata": metadata or {},
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return cached_path
