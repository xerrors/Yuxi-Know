from __future__ import annotations

from pathlib import Path, PurePosixPath

from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import (
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

from yuxi.agents.skills.service import get_skills_root_dir, is_valid_skill_slug


class SelectedSkillsReadonlyBackend(FilesystemBackend):
    """只读 skills backend，仅暴露选中的技能目录。"""

    def __init__(self, *, selected_slugs: list[str] | None, root_dir: Path | None = None):
        super().__init__(root_dir=root_dir or get_skills_root_dir(), virtual_mode=True)
        self._selected_slugs = {
            str(slug).strip()
            for slug in (selected_slugs or [])
            if isinstance(slug, str) and is_valid_skill_slug(str(slug))
        }

    def _extract_slug(self, path: str | None) -> str | None:
        if not path:
            return None
        normalized = (path or "").strip()
        if not normalized or normalized == "/":
            return None
        pure = PurePosixPath(normalized if normalized.startswith("/") else f"/{normalized}")
        parts = [p for p in pure.parts if p not in ("/", "")]
        return parts[0] if parts else None

    def _is_allowed_path(self, path: str | None) -> bool:
        slug = self._extract_slug(path)
        if slug is None:
            return True
        return slug in self._selected_slugs

    def _is_allowed_file(self, file_path: str) -> bool:
        slug = self._extract_slug(file_path)
        return slug is not None and slug in self._selected_slugs

    def _filter_infos(self, infos: list[FileInfo]) -> list[FileInfo]:
        return [item for item in infos if self._extract_slug(item.get("path", "")) in self._selected_slugs]

    def _filter_matches(self, matches: list[GrepMatch]) -> list[GrepMatch]:
        return [item for item in matches if self._extract_slug(item.get("path", "")) in self._selected_slugs]

    def ls(self, path: str) -> LsResult:
        if not self._selected_slugs:
            return LsResult(entries=[])

        normalized = (path or "/").strip() or "/"
        if not self._is_allowed_path(normalized):
            return LsResult(error="Access denied: path is outside selected skills.")

        result = super().ls(normalized)
        if result.error:
            return result
        infos = result.entries or []
        if normalized == "/":
            infos = self._filter_infos(infos)
        return LsResult(entries=infos)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        if not self._is_allowed_file(file_path):
            return ReadResult(error="Access denied: file is outside selected skills.")
        return super().read(file_path, offset=offset, limit=limit)

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None) -> GrepResult:
        if not self._selected_slugs:
            return GrepResult(matches=[])

        if path is not None:
            if not self._is_allowed_path(path):
                return GrepResult(error="Access denied: path is outside selected skills.")
            result = super().grep(pattern=pattern, path=path, glob=glob)
            if result.error:
                return result
            return GrepResult(matches=self._filter_matches(result.matches or []))

        matches: list[GrepMatch] = []
        for slug in sorted(self._selected_slugs):
            result = super().grep(pattern=pattern, path=f"/{slug}", glob=glob)
            if result.error:
                continue
            matches.extend(result.matches or [])
        return GrepResult(matches=matches)

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        if not self._selected_slugs:
            return GlobResult(matches=[])
        if not self._is_allowed_path(path):
            return GlobResult(error="Access denied: path is outside selected skills.")
        result = super().glob(pattern=pattern, path=path)
        if result.error:
            return result
        return GlobResult(matches=self._filter_infos(result.matches or []))

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error="Skills path is read-only.")

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return EditResult(error="Skills path is read-only.")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not self._is_allowed_file(path):
                responses.append(FileDownloadResponse(path=path, content=None, error="invalid_path"))
                continue
            target = self._resolve_path(path)
            if not target.exists():
                responses.append(FileDownloadResponse(path=path, content=None, error="file_not_found"))
                continue
            if target.is_dir():
                responses.append(FileDownloadResponse(path=path, content=None, error="is_directory"))
                continue
            responses.append(FileDownloadResponse(path=path, content=target.read_bytes(), error=None))
        return responses
