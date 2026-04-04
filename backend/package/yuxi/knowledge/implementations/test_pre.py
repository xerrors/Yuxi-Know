import asyncio
import json
import re
from typing import Any

from yuxi import config
from yuxi.knowledge.base import FileStatus, KnowledgeBase
from yuxi.models.chat import select_model
from yuxi.utils import logger
from yuxi.utils.datetime_utils import utc_isoformat

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,}")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")


class TestPreKB(KnowledgeBase):
    """基于纯文本扫描的测试知识库实现"""

    def __init__(self, work_dir: str, **kwargs):
        del kwargs
        super().__init__(work_dir)
        self._metadata_lock = asyncio.Lock()

    @property
    def kb_type(self) -> str:
        return "test_pre"

    async def _create_kb_instance(self, db_id: str, config: dict) -> Any:
        del db_id, config
        return None

    async def _initialize_kb_instance(self, instance: Any) -> None:
        del instance
        return None

    async def index_file(self, db_id: str, file_id: str, operator_id: str | None = None) -> dict:
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")
        if file_id not in self.files_meta:
            raise ValueError(f"File {file_id} not found")

        file_meta = self.files_meta[file_id]
        current_status = file_meta.get("status")
        allowed_statuses = {
            FileStatus.PARSED,
            FileStatus.ERROR_INDEXING,
            FileStatus.INDEXED,
            "done",
        }
        if current_status not in allowed_statuses:
            raise ValueError(
                f"Cannot index file with status '{current_status}'. "
                f"File must be parsed first (status should be one of: {', '.join(sorted(allowed_statuses))})"
            )
        if not file_meta.get("markdown_file"):
            raise ValueError("File has not been parsed yet (no markdown_file)")

        if "error" in file_meta:
            self.files_meta[file_id].pop("error", None)

        self.files_meta[file_id]["status"] = FileStatus.INDEXING
        self.files_meta[file_id]["updated_at"] = utc_isoformat()
        if operator_id:
            self.files_meta[file_id]["updated_by"] = operator_id
        await self._persist_file(file_id)
        self._add_to_processing_queue(file_id)

        try:
            self.files_meta[file_id]["status"] = FileStatus.INDEXED
            self.files_meta[file_id]["updated_at"] = utc_isoformat()
            if operator_id:
                self.files_meta[file_id]["updated_by"] = operator_id
            await self._persist_file(file_id)
            return self.files_meta[file_id]
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            logger.error(f"Failed to index test_pre file {file_id}: {error_msg}")
            self.files_meta[file_id]["status"] = FileStatus.ERROR_INDEXING
            self.files_meta[file_id]["error"] = error_msg
            self.files_meta[file_id]["updated_at"] = utc_isoformat()
            if operator_id:
                self.files_meta[file_id]["updated_by"] = operator_id
            await self._persist_file(file_id)
            raise
        finally:
            self._remove_from_processing_queue(file_id)

    async def update_content(self, db_id: str, file_ids: list[str], params: dict | None = None) -> list[dict]:
        results: list[dict] = []
        for file_id in file_ids:
            if params:
                await self.update_file_params(db_id, file_id, params)
            await self.parse_file(db_id, file_id)
            results.append(await self.index_file(db_id, file_id))
        return results

    async def aquery(self, query_text: str, db_id: str, agent_call: bool = False, **kwargs) -> list[dict]:
        del agent_call
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        query_params = self._get_query_params(db_id)
        merged = {**query_params, **kwargs}

        keyword_count = max(int(merged.get("keyword_count", 5) or 5), 1)
        snippet_line_window = max(int(merged.get("snippet_line_window", 30) or 30), 0)
        final_top_k = max(int(merged.get("final_top_k", 10) or 10), 1)
        max_snippet_chars = max(int(merged.get("max_snippet_chars", 15000) or 15000), 200)
        file_name_filter = str(merged.get("file_name") or "").strip().lower()

        keywords = await self._generate_keywords(query_text, keyword_count)
        if not keywords:
            return []

        snippets: list[dict[str, Any]] = []
        for file_id, file_meta in self.files_meta.items():
            if file_meta.get("database_id") != db_id:
                continue
            if file_meta.get("is_folder"):
                continue
            if file_meta.get("status") != FileStatus.INDEXED:
                continue
            filename = str(file_meta.get("filename") or "")
            if file_name_filter and file_name_filter not in filename.lower():
                continue

            text_content = await self._read_text_for_query(file_meta)
            if not text_content:
                continue

            file_snippets = self._build_snippets_for_text(
                text=text_content,
                file_id=file_id,
                filename=filename,
                keywords=keywords,
                window=snippet_line_window,
                max_chars=max_snippet_chars,
            )
            snippets.extend(file_snippets)

        snippets.sort(
            key=lambda item: (
                item.get("score", 0.0),
                -int(item.get("metadata", {}).get("start_line", 1) or 1),
            ),
            reverse=True,
        )

        results: list[dict] = []
        for idx, snippet in enumerate(snippets[:final_top_k]):
            metadata = dict(snippet["metadata"])
            metadata["chunk_index"] = idx
            metadata["chunk_id"] = metadata.get("chunk_id") or (
                f"{metadata.get('file_id', 'file')}:{metadata.get('start_line', 1)}-{metadata.get('end_line', 1)}"
            )
            results.append(
                {
                    "content": snippet["content"],
                    "score": float(snippet.get("score") or 0.0),
                    "metadata": metadata,
                }
            )
        return results

    def get_query_params_config(self, db_id: str, **kwargs) -> dict:
        del db_id, kwargs
        options = [
            {
                "key": "keyword_count",
                "label": "关键词数量",
                "type": "number",
                "default": 5,
                "min": 1,
                "max": 10,
                "description": "从查询中抽取的关键词数量",
            },
            {
                "key": "snippet_line_window",
                "label": "上下文行数",
                "type": "number",
                "default": 30,
                "min": 0,
                "max": 200,
                "description": "命中行前后扩展的行数",
            },
            {
                "key": "final_top_k",
                "label": "返回片段数",
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 100,
                "description": "最终返回的文本片段数量",
            },
            {
                "key": "max_snippet_chars",
                "label": "单片段最大字符数",
                "type": "number",
                "default": 15000,
                "min": 200,
                "max": 50000,
                "description": "每个匹配片段的最大字符数",
            },
        ]
        return {"type": "test_pre", "options": options}

    async def _read_text_for_query(self, file_meta: dict) -> str:
        markdown_file = str(file_meta.get("markdown_file") or "").strip()
        if markdown_file:
            return await self._read_markdown_from_minio(markdown_file)
        return ""

    async def _generate_keywords(self, query_text: str, keyword_count: int) -> list[str]:
        fallback_keywords = self._fallback_keywords(query_text, keyword_count)
        try:
            model = select_model(model_spec=config.default_model)
            message = [
                {
                    "role": "system",
                    "content": (
                        "你是关键词提取器。请从用户问题中提取最适合文本检索的关键词。"
                        "仅返回 JSON 数组，例如 [\"关键词1\", \"关键词2\"]，不要输出额外说明。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"问题：{query_text}\n请返回不超过 {keyword_count} 个关键词。",
                },
            ]
            response = await model.call(message, stream=False)
            content = getattr(response, "content", "") or ""
            parsed_keywords = self._parse_keywords_from_response(content, keyword_count)
            return parsed_keywords or fallback_keywords
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"test_pre keyword extraction fallback for query={query_text!r}: {exc}")
            return fallback_keywords

    @staticmethod
    def _parse_keywords_from_response(content: str, keyword_count: int) -> list[str]:
        if not content:
            return []

        candidates: list[str] = []
        try:
            data = json.loads(content)
            if isinstance(data, list):
                candidates = [str(item).strip() for item in data]
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", content)
            if match:
                try:
                    data = json.loads(match.group(0))
                    if isinstance(data, list):
                        candidates = [str(item).strip() for item in data]
                except json.JSONDecodeError:
                    pass

        if not candidates:
            candidates = [part.strip() for part in re.split(r"[,\n、，；;]+", content) if part.strip()]

        return TestPreKB._unique_keywords(candidates, keyword_count)

    @staticmethod
    def _fallback_keywords(query_text: str, keyword_count: int) -> list[str]:
        candidates = _CJK_TOKEN_RE.findall(query_text) + _ASCII_TOKEN_RE.findall(query_text)
        if not candidates and query_text.strip():
            candidates = [query_text.strip()]
        return TestPreKB._unique_keywords(candidates, keyword_count)

    @staticmethod
    def _unique_keywords(candidates: list[str], keyword_count: int) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            keyword = str(candidate or "").strip()
            if not keyword:
                continue
            normalized = keyword.lower()
            if normalized in seen:
                continue
            deduped.append(keyword)
            seen.add(normalized)
            if len(deduped) >= keyword_count:
                break
        return deduped

    @staticmethod
    def _line_match_keywords(line: str, keywords: list[str]) -> list[str]:
        lowered = line.lower()
        matched: list[str] = []
        for keyword in keywords:
            token = keyword.lower()
            if token and token in lowered:
                matched.append(keyword)
        return matched

    def _build_snippets_for_text(
        self,
        *,
        text: str,
        file_id: str,
        filename: str,
        keywords: list[str],
        window: int,
        max_chars: int,
    ) -> list[dict[str, Any]]:
        lines = text.splitlines()
        raw_matches: list[dict[str, Any]] = []

        for idx, line in enumerate(lines):
            matched_keywords = self._line_match_keywords(line, keywords)
            if not matched_keywords:
                continue
            start = max(0, idx - window)
            end = min(len(lines) - 1, idx + window)
            raw_matches.append(
                {
                    "start_line": start + 1,
                    "end_line": end + 1,
                    "match_keywords": matched_keywords,
                }
            )

        if not raw_matches:
            return []

        merged_matches: list[dict[str, Any]] = []
        for match in raw_matches:
            if not merged_matches or match["start_line"] > merged_matches[-1]["end_line"]:
                merged_matches.append(match)
                continue
            previous = merged_matches[-1]
            previous["end_line"] = max(previous["end_line"], match["end_line"])
            previous["match_keywords"] = sorted(
                set(previous.get("match_keywords", [])) | set(match.get("match_keywords", [])),
                key=lambda item: keywords.index(item) if item in keywords else len(keywords),
            )

        snippets: list[dict[str, Any]] = []
        for merged in merged_matches:
            start_idx = int(merged["start_line"]) - 1
            end_idx = int(merged["end_line"])
            content = "\n".join(lines[start_idx:end_idx]).strip()
            if len(content) > max_chars:
                content = content[: max_chars - 1].rstrip() + "…"

            matched_keywords = list(merged.get("match_keywords", []))
            score = float(len(matched_keywords))
            snippets.append(
                {
                    "content": content,
                    "score": score,
                    "metadata": {
                        "source": filename or file_id,
                        "file_id": file_id,
                        "chunk_id": f"{file_id}:{merged['start_line']}-{merged['end_line']}",
                        "chunk_index": 0,
                        "start_line": merged["start_line"],
                        "end_line": merged["end_line"],
                        "match_keywords": matched_keywords,
                    },
                }
            )
        return snippets
