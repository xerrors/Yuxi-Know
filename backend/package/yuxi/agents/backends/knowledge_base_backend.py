from __future__ import annotations

import fnmatch
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import EditResult, FileDownloadResponse, FileInfo, FileUploadResponse, WriteResult

from yuxi import config as conf
from yuxi import knowledge_base
from yuxi.knowledge.utils.kb_utils import is_minio_url, parse_minio_url
from yuxi.storage.minio import get_minio_client

KBS_PATH = "/home/gem/kbs"
_INVALID_SEGMENT_RE = re.compile(r"[\\/\x00-\x1f\x7f]+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class _MaterializedFile:
    virtual_path: str
    cache_path: Path
    source_path: str
    modified_at: str | None = None


def _normalize_virtual_path(path: str | None) -> str:
    raw = str(path or "").strip() or "/"
    normalized = "/" + raw.lstrip("/")
    pure = PurePosixPath(normalized)
    if ".." in pure.parts:
        raise ValueError("path traversal is not allowed")
    return str(pure)


def _sanitize_segment(value: str | None, fallback: str) -> str:
    cleaned = str(value or "").strip()
    cleaned = _INVALID_SEGMENT_RE.sub("_", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    if not cleaned or cleaned in {".", ".."}:
        return fallback
    return cleaned


def _candidate_name(file_meta: dict[str, Any]) -> str:
    filename = str(file_meta.get("filename") or "").strip()
    if filename:
        return filename

    original = str(file_meta.get("original_filename") or "").strip()
    if original:
        return original

    for key in ("path", "markdown_file"):
        raw = str(file_meta.get(key) or "").strip()
        if raw:
            try:
                parsed = PurePosixPath(raw)
                name = parsed.name
            except Exception:  # noqa: BLE001
                name = ""
            if name:
                return name

    return str(file_meta.get("file_id") or "")


def _unique_name(base_name: str, *, stable_id: str, used_names: set[str]) -> str:
    if base_name not in used_names:
        used_names.add(base_name)
        return base_name

    suffix = f"__{stable_id[:8]}"
    candidate = f"{base_name}{suffix}"
    while candidate in used_names:
        suffix = f"__{stable_id}"
        candidate = f"{base_name}{suffix}"
    used_names.add(candidate)
    return candidate


def _materialize_text_view(content: bytes, file_path: str, *, offset: int = 0, limit: int = 2000) -> str:
    if not content:
        return "System reminder: File exists but has empty contents"

    if b"\x00" in content:
        return f"Error: File '{file_path}' is binary and cannot be rendered as text"

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return f"Error: File '{file_path}' is binary and cannot be rendered as text"

    lines = text.splitlines()
    start = max(0, int(offset))
    selected = lines[start : start + int(limit)]
    return "\n".join(f"{start + idx + 1:6d}\t{line}" for idx, line in enumerate(selected))


async def resolve_visible_knowledge_bases_for_context(context) -> list[dict[str, Any]]:
    user_id = getattr(context, "user_id", None)
    if not user_id:
        setattr(context, "_visible_knowledge_bases", [])
        return []

    enabled_names = {str(name).strip() for name in (getattr(context, "knowledges", None) or []) if str(name).strip()}
    if not enabled_names:
        setattr(context, "_visible_knowledge_bases", [])
        return []

    try:
        raw_user_id = int(user_id)
    except (TypeError, ValueError):
        setattr(context, "_visible_knowledge_bases", [])
        return []

    result = await knowledge_base.get_databases_by_raw_id(raw_user_id)
    databases = [db for db in (result.get("databases") or []) if str(db.get("name") or "").strip() in enabled_names]
    setattr(context, "_visible_knowledge_bases", databases)
    return databases


def _all_files_meta() -> dict[str, dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}
    for kb_instance in getattr(knowledge_base, "kb_instances", {}).values():
        for file_id, meta in getattr(kb_instance, "files_meta", {}).items():
            aggregated[str(file_id)] = meta
    return aggregated


class KnowledgeBaseReadonlyBackend(FilesystemBackend):
    def __init__(self, *, visible_kbs: list[dict[str, Any]] | None, cache_root: Path | str | None = None):
        self._cache_root = Path(cache_root or (Path(conf.save_dir) / "knowledge_base_data" / "kb-cache")).resolve()
        self._cache_root.mkdir(parents=True, exist_ok=True)
        super().__init__(root_dir=self._cache_root, virtual_mode=True)
        self._visible_kbs = list(visible_kbs or [])
        self._entries_by_dir: dict[str, list[FileInfo]] = defaultdict(list)
        self._dir_paths: set[str] = {"/"}
        self._files: dict[str, _MaterializedFile] = {}
        self._all_files: list[FileInfo] = []
        self._build_virtual_tree()

    def has_entries(self) -> bool:
        return bool(self._visible_kbs)

    def _build_virtual_tree(self) -> None:
        kb_name_candidates = {
            str(db.get("db_id") or db.get("name") or f"kb-{index}"): _sanitize_segment(
                db.get("name"),
                str(db.get("db_id") or f"kb-{index}"),
            )
            for index, db in enumerate(self._visible_kbs)
        }
        used_root_names: set[str] = set()
        kb_virtual_names: dict[str, str] = {}
        sorted_kbs = sorted(
            self._visible_kbs,
            key=lambda item: (str(item.get("name") or ""), str(item.get("db_id") or "")),
        )
        for db in sorted_kbs:
            db_id = str(db.get("db_id") or "")
            if not db_id:
                continue
            base_name = kb_name_candidates.get(db_id) or db_id
            kb_virtual_names[db_id] = _unique_name(base_name, stable_id=db_id, used_names=used_root_names)

        files_by_db: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for file_id, meta in _all_files_meta().items():
            db_id = str(meta.get("database_id") or "")
            if db_id in kb_virtual_names:
                files_by_db[db_id][str(file_id)] = meta

        for db_id, kb_virtual_name in kb_virtual_names.items():
            kb_root = f"/{kb_virtual_name}"
            self._add_entry("/", kb_root, is_dir=True)
            records = files_by_db.get(db_id, {})
            self._build_source_tree(db_id=db_id, kb_root=kb_root, records=records)
            self._build_parsed_tree(db_id=db_id, kb_root=kb_root, records=records)

        for path, entries in list(self._entries_by_dir.items()):
            entries.sort(key=lambda item: str(item.get("path") or ""))
            self._entries_by_dir[path] = entries
        self._all_files = sorted(self._all_files, key=lambda item: str(item.get("path") or ""))

    def _build_source_tree(self, *, db_id: str, kb_root: str, records: dict[str, dict[str, Any]]) -> None:
        children_by_parent: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for file_id, meta in records.items():
            parent_id = meta.get("parent_id")
            children_by_parent[str(parent_id) if parent_id else None].append({"file_id": file_id, "meta": meta})

        resolved_parent_paths: dict[str, str] = {}
        resolved_source_names: dict[str, str] = {}

        def walk(parent_id: str | None, parent_path: str) -> None:
            siblings = children_by_parent.get(parent_id, [])
            used_names: set[str] = set()
            candidates: list[tuple[dict[str, Any], str]] = []
            for item in siblings:
                file_id = item["file_id"]
                meta = item["meta"]
                base_name = _sanitize_segment(_candidate_name(meta), file_id)
                candidates.append((item, base_name))

            for item, base_name in sorted(candidates, key=lambda pair: (pair[1], pair[0]["file_id"])):
                file_id = item["file_id"]
                meta = item["meta"]
                unique_name = _unique_name(base_name, stable_id=file_id, used_names=used_names)
                child_path = f"{parent_path.rstrip('/')}/{unique_name}" if parent_path != "/" else f"/{unique_name}"
                if meta.get("is_folder"):
                    modified_at = meta.get("updated_at") or meta.get("created_at")
                    self._add_entry(parent_path, child_path, is_dir=True, modified_at=modified_at)
                    walk(file_id, child_path)
                    continue

                self._add_entry(
                    parent_path,
                    child_path,
                    is_dir=False,
                    size=int(meta.get("size") or 0),
                    modified_at=meta.get("updated_at") or meta.get("created_at"),
                )
                resolved_parent_paths[file_id] = parent_path
                resolved_source_names[file_id] = unique_name
                cache_path = self._cache_root / db_id / "source" / file_id / unique_name
                self._files[child_path] = _MaterializedFile(
                    virtual_path=child_path,
                    cache_path=cache_path,
                    source_path=str(meta.get("path") or ""),
                    modified_at=meta.get("updated_at") or meta.get("created_at"),
                )
                self._all_files.append(
                    {
                        "path": child_path,
                        "is_dir": False,
                        "size": int(meta.get("size") or 0),
                        "modified_at": str(meta.get("updated_at") or meta.get("created_at") or ""),
                    }
                )

        walk(None, kb_root)
        self._resolved_parent_paths = getattr(self, "_resolved_parent_paths", {})
        self._resolved_parent_paths[db_id] = resolved_parent_paths
        self._resolved_source_names = getattr(self, "_resolved_source_names", {})
        self._resolved_source_names[db_id] = resolved_source_names

    def _build_parsed_tree(self, *, db_id: str, kb_root: str, records: dict[str, dict[str, Any]]) -> None:
        parsed_records = {
            file_id: meta
            for file_id, meta in records.items()
            if not meta.get("is_folder") and str(meta.get("markdown_file") or "").strip()
        }
        if not parsed_records:
            return

        parsed_root = f"{kb_root}/parsed"
        self._add_entry(kb_root, parsed_root, is_dir=True)
        parent_paths = getattr(self, "_resolved_parent_paths", {}).get(db_id, {})
        source_names = getattr(self, "_resolved_source_names", {}).get(db_id, {})

        grouped: dict[str, list[tuple[str, dict[str, Any], str]]] = defaultdict(list)
        for file_id, meta in parsed_records.items():
            source_parent = parent_paths.get(file_id, kb_root)
            parsed_parent = (
                f"{parsed_root}{source_parent[len(kb_root) :]}" if source_parent.startswith(kb_root) else parsed_root
            )
            source_name = source_names.get(file_id) or _sanitize_segment(meta.get("filename"), file_id)
            source_stem = PurePosixPath(source_name).stem or source_name or file_id
            base_name = _sanitize_segment(f"{source_stem}.md", f"{file_id}.md")
            grouped[parsed_parent].append((file_id, meta, base_name))

        for parsed_parent, items in grouped.items():
            current = PurePosixPath(parsed_parent)
            while str(current) not in {"", "."} and str(current) != "/":
                current_str = str(current)
                parent_str = str(current.parent) if str(current.parent) != "." else "/"
                if current_str not in self._dir_paths:
                    self._add_entry(parent_str, current_str, is_dir=True)
                current = current.parent

            used_names: set[str] = set()
            for file_id, meta, base_name in sorted(items, key=lambda item: (item[2], item[0])):
                unique_name = _unique_name(base_name, stable_id=file_id, used_names=used_names)
                file_path = f"{parsed_parent.rstrip('/')}/{unique_name}" if parsed_parent != "/" else f"/{unique_name}"
                self._add_entry(
                    parsed_parent,
                    file_path,
                    is_dir=False,
                    size=0,
                    modified_at=meta.get("updated_at") or meta.get("created_at"),
                )
                cache_path = self._cache_root / db_id / "parsed" / f"{file_id}.md"
                self._files[file_path] = _MaterializedFile(
                    virtual_path=file_path,
                    cache_path=cache_path,
                    source_path=str(meta.get("markdown_file") or ""),
                    modified_at=meta.get("updated_at") or meta.get("created_at"),
                )
                self._all_files.append(
                    {
                        "path": file_path,
                        "is_dir": False,
                        "size": 0,
                        "modified_at": str(meta.get("updated_at") or meta.get("created_at") or ""),
                    }
                )

    def _add_entry(
        self,
        parent_path: str,
        child_path: str,
        *,
        is_dir: bool,
        size: int = 0,
        modified_at: str | None = None,
    ) -> None:
        normalized_parent = _normalize_virtual_path(parent_path)
        normalized_child = _normalize_virtual_path(child_path)
        entry_path = f"{normalized_child}/" if is_dir else normalized_child
        entry: FileInfo = {
            "path": entry_path,
            "is_dir": is_dir,
            "size": int(size or 0),
            "modified_at": str(modified_at or ""),
        }
        if entry_path not in {str(item.get("path")) for item in self._entries_by_dir[normalized_parent]}:
            self._entries_by_dir[normalized_parent].append(entry)
        if is_dir:
            self._dir_paths.add(normalized_child)
            self._entries_by_dir.setdefault(normalized_child, [])

    def _ensure_local_file(self, descriptor: _MaterializedFile) -> Path:
        if descriptor.cache_path.exists():
            return descriptor.cache_path

        source = descriptor.source_path.strip()
        if not source:
            raise FileNotFoundError(descriptor.virtual_path)
        if not is_minio_url(source):
            raise FileNotFoundError(descriptor.virtual_path)

        bucket_name, object_name = parse_minio_url(source)
        payload = get_minio_client().download_file(bucket_name, object_name)
        descriptor.cache_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor.cache_path.write_bytes(payload)
        return descriptor.cache_path

    def ls_info(self, path: str) -> list[FileInfo]:
        normalized_path = _normalize_virtual_path(path)
        return list(self._entries_by_dir.get(normalized_path, []))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        normalized_path = _normalize_virtual_path(file_path)
        descriptor = self._files.get(normalized_path)
        if descriptor is None:
            if normalized_path in self._dir_paths:
                return f"Error: Path '{file_path}' is a directory"
            return f"Error: File '{file_path}' not found"

        try:
            content = self._ensure_local_file(descriptor).read_bytes()
        except FileNotFoundError:
            return f"Error: File '{file_path}' not found"
        except Exception as exc:  # noqa: BLE001
            detail = str(exc).strip() or "unknown error"
            return f"Error: Failed to read '{file_path}': {detail}"

        return _materialize_text_view(content, file_path, offset=offset, limit=limit)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        normalized_path = _normalize_virtual_path(path)
        if ".." in PurePosixPath(pattern).parts:
            raise ValueError("Path traversal not allowed in glob pattern")
        normalized_pattern = pattern.lstrip("/") or "*"
        prefix = "/" if normalized_path == "/" else f"{normalized_path.rstrip('/')}/"

        matches: list[FileInfo] = []
        for item in self._all_files:
            item_path = str(item.get("path") or "")
            if normalized_path != "/" and not item_path.startswith(prefix):
                continue
            relative = item_path[len(prefix) :] if normalized_path != "/" else item_path.lstrip("/")
            if fnmatch.fnmatch(relative, normalized_pattern):
                matches.append(dict(item))
        return matches

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None) -> list[dict[str, Any]] | str:
        normalized_path = _normalize_virtual_path(path or "/")
        prefix = "/" if normalized_path == "/" else f"{normalized_path.rstrip('/')}/"
        if normalized_path in self._files:
            targets = [normalized_path]
        else:
            targets = [
                item["path"]
                for item in self._all_files
                if normalized_path == "/" or str(item["path"]).startswith(prefix)
            ]

        matches: list[dict[str, Any]] = []
        for target in targets:
            display_target = str(target)
            relative = display_target.lstrip("/") if normalized_path == "/" else display_target[len(prefix) :]
            if glob and not fnmatch.fnmatch(relative, glob):
                continue
            descriptor = self._files.get(display_target)
            if descriptor is None:
                continue
            try:
                content = self._ensure_local_file(descriptor).read_bytes()
                if b"\x00" in content:
                    continue
                text = content.decode("utf-8")
            except Exception:  # noqa: BLE001
                continue
            for line_num, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    matches.append({"path": display_target, "line": line_num, "text": line})
        return matches

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error="Knowledge base path is read-only.")

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return EditResult(error="Knowledge base path is read-only.")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error="permission_denied") for path, _content in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                normalized_path = _normalize_virtual_path(path)
            except ValueError:
                responses.append(FileDownloadResponse(path=path, content=None, error="invalid_path"))
                continue

            descriptor = self._files.get(normalized_path)
            if descriptor is None:
                if normalized_path in self._dir_paths:
                    responses.append(FileDownloadResponse(path=path, content=None, error="is_directory"))
                else:
                    responses.append(FileDownloadResponse(path=path, content=None, error="file_not_found"))
                continue

            try:
                content = self._ensure_local_file(descriptor).read_bytes()
            except FileNotFoundError:
                responses.append(FileDownloadResponse(path=path, content=None, error="file_not_found"))
                continue
            except ValueError:
                responses.append(FileDownloadResponse(path=path, content=None, error="invalid_path"))
                continue

            responses.append(FileDownloadResponse(path=path, content=content, error=None))
        return responses
