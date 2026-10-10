from __future__ import annotations

import hashlib
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import yuxi.workspace.preview as file_preview
from fastapi import HTTPException, UploadFile
from yuxi.services import workspace_service as svc
from yuxi.workspace import paths as workspace_paths


def _user() -> SimpleNamespace:
    return SimpleNamespace(id="db-id-1", uid="user-1")


def _workspace_root(user: SimpleNamespace) -> Path:
    svc._workspace_backend(user)
    return workspace_paths.user_workspace_dir(str(user.uid))


def test_workspace_root_creates_default_agent_context_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))

    previous_umask = os.umask(0o077)
    try:
        root = _workspace_root(_user())
    finally:
        os.umask(previous_umask)

    assert root == tmp_path / "threads" / "shared" / "user-1" / "workspace"
    assert (root / "agents" / "AGENTS.md").read_text(encoding="utf-8") == (
        "# AGENTS\n\n以下是约束 Agent 行为的一些要求\n"
    )
    assert (root / "agents" / "USER.md").read_text(encoding="utf-8") == ("# USER\n\n以下是有关用户的一些信息\n")
    assert (root / "agents" / "MEMORY.md").read_text(encoding="utf-8") == (
        "# MEMORY\n\n以下是 Agent 需要记住的一些信息\n"
    )
    assert {path.name for path in (root / "agents").iterdir()} == {"AGENTS.md", "USER.md", "MEMORY.md"}
    assert (root / "agents").stat().st_mode & 0o777 == 0o700
    for filename in ("AGENTS.md", "USER.md", "MEMORY.md"):
        assert (root / "agents" / filename).stat().st_mode & 0o777 == 0o600


def test_external_uid_uses_stable_path_safe_workspace_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    uid = "oidc:898f3d04-140e-433b-a06e-1e50a2bd01b6"

    workspace_paths.ensure_user_workspace(uid)

    dirname = "uid-" + hashlib.sha256(uid.encode("utf-8")).hexdigest()
    workspace = workspace_paths.user_workspace_dir(uid)
    assert workspace == tmp_path / "threads" / "shared" / dirname / "workspace"
    assert (workspace / "agents" / "AGENTS.md").is_file()


@pytest.mark.parametrize("uid", ["../outside", r"C:\\outside", "oidc:tenant/user"])
def test_external_uid_cannot_escape_threads_root(tmp_path: Path, monkeypatch, uid: str) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "saves" / "threads"))

    workspace = workspace_paths.user_workspace_dir(uid)

    assert workspace.parent.name == "uid-" + hashlib.sha256(uid.encode("utf-8")).hexdigest()
    assert workspace.resolve().is_relative_to((tmp_path / "saves" / "threads").resolve())


def test_workspace_root_keeps_existing_agents_prompt_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    agents_dir = tmp_path / "threads" / "shared" / "user-1" / "workspace" / "agents"
    agents_dir.mkdir(parents=True)
    agents_file = agents_dir / "AGENTS.md"
    agents_file.write_text("保留已有内容", encoding="utf-8")

    root = _workspace_root(_user())

    assert root == tmp_path / "threads" / "shared" / "user-1" / "workspace"
    assert agents_file.read_text(encoding="utf-8") == "保留已有内容"


def test_workspace_root_rejects_symlink_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user_root = tmp_path / "threads" / "shared" / "user-1"
    outside_root = tmp_path / "outside"
    user_root.mkdir(parents=True)
    outside_root.mkdir()
    (user_root / "workspace").symlink_to(outside_root, target_is_directory=True)

    with pytest.raises(HTTPException) as exc_info:
        svc._workspace_backend(_user())

    assert exc_info.value.status_code == 403


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("bad.txt", b"\xff\xfe\x00"),
        ("sheet.xlsm", b"PK\x03\x04excel"),
    ],
)
@pytest.mark.asyncio
async def test_read_workspace_file_content_returns_unsupported_for_unreadable_files(
    tmp_path: Path,
    monkeypatch,
    filename: str,
    content: bytes,
) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user = _user()
    root = _workspace_root(user)
    target = root / filename
    target.write_bytes(content)

    result = await svc.read_workspace_file_content(path=f"/{filename}", current_user=user)

    assert result["content"] is None
    assert result["preview_type"] == "unsupported"
    assert result["supported"] is False


@pytest.mark.parametrize("filename", ["demo.docx", "slides.pptx", "sheet.xlsx", "sheet.xls"])
@pytest.mark.asyncio
async def test_read_workspace_file_content_returns_pdf_preview_for_office_file(
    tmp_path: Path,
    monkeypatch,
    filename: str,
) -> None:
    """Office 与 Excel 文件返回可展示的 PDF 响应。"""
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user = _user()
    root = _workspace_root(user)
    target = root / filename
    target.write_bytes(b"office")

    async def fake_convert(name: str, content: bytes) -> bytes:
        assert name == filename
        assert content == b"office"
        return b"%PDF-1.4\npreview"

    monkeypatch.setenv("YUXI_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(file_preview, "convert_office_to_pdf", fake_convert)

    result = await svc.read_workspace_file_content(path=f"/{filename}", current_user=user)
    body = result.body
    assert result.headers["content-length"] == str(len(body))

    assert result.media_type == "application/pdf"
    assert result.headers["x-yuxi-preview-type"] == "pdf"
    assert body == b"%PDF-1.4\npreview"


@pytest.mark.asyncio
async def test_read_workspace_file_content_reports_excel_conversion_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user = _user()
    root = _workspace_root(user)
    target = root / "sheet.xlsx"
    target.write_bytes(b"PK\x03\x04excel")

    async def fail_convert(filename: str, content: bytes) -> bytes:
        """模拟转换器明确拒绝损坏表格。"""
        from yuxi.utils.filepreview import OfficePreviewConversionError

        raise OfficePreviewConversionError("表格已损坏")

    monkeypatch.setenv("YUXI_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(file_preview, "convert_office_to_pdf", fail_convert)
    with pytest.raises(HTTPException) as exc_info:
        await svc.read_workspace_file_content(path="/sheet.xlsx", current_user=user)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "表格已损坏"


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("demo.docx", b"office"),
        ("slides.pptx", b"presentation"),
        ("sheet.xlsx", b"spreadsheet"),
        ("sheet.xls", b"legacy spreadsheet"),
    ],
)
@pytest.mark.asyncio
async def test_preview_workspace_file_caches_office_pdf_conversion(
    tmp_path: Path,
    monkeypatch,
    filename: str,
    content: bytes,
) -> None:
    save_dir = tmp_path / "saves"
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(save_dir / "threads"))
    monkeypatch.setenv("YUXI_RUNTIME_DIR", str(runtime_dir))
    user = _user()
    root = _workspace_root(user)
    target = root / filename
    target.write_bytes(content)

    convert_calls = 0

    async def fake_convert(name: str, _raw: bytes) -> bytes:
        nonlocal convert_calls
        assert name == filename
        convert_calls += 1
        return b"%PDF-1.4\npreview"

    monkeypatch.setattr(file_preview, "convert_office_to_pdf", fake_convert)

    async def read_pdf() -> bytes:
        response = await svc.read_workspace_file_content(path=f"/{filename}", current_user=user)
        assert response.media_type == "application/pdf"
        assert response.headers["x-yuxi-preview-type"] == "pdf"
        assert response.headers["content-length"] == str(len(response.body))
        return response.body

    assert await read_pdf() == b"%PDF-1.4\npreview"
    assert await read_pdf() == b"%PDF-1.4\npreview"
    assert convert_calls == 1
    assert list((runtime_dir / "cache" / "office-previews").rglob("*.pdf"))
    assert not list(save_dir.rglob(".office_preview_cache"))

    target.write_bytes(content + b"-v2")
    assert await read_pdf() == b"%PDF-1.4\npreview"
    assert convert_calls == 2


@pytest.mark.asyncio
async def test_download_workspace_file_keeps_office_original_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user = _user()
    root = _workspace_root(user)
    target = root / "slides.pptx"
    target.write_bytes(b"presentation")

    response = await svc.download_workspace_file(path="/slides.pptx", current_user=user)
    body = Path(response.path).read_bytes()
    await response.background()

    assert response.media_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    assert body == b"presentation"


@pytest.mark.parametrize(
    ("extension", "original", "content"),
    [
        ("md", "旧内容", "# 新内容"),
        ("txt", "old", "new"),
    ],
)
@pytest.mark.asyncio
async def test_write_workspace_file_content_updates_file(
    tmp_path: Path,
    monkeypatch,
    extension: str,
    original: str,
    content: str,
) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user = _user()
    root = _workspace_root(user)
    target = root / f"note.{extension}"
    target.write_text(original, encoding="utf-8")

    result = await svc.write_workspace_file_content(path=f"/note.{extension}", content=content, current_user=user)

    assert result["success"] is True
    assert result["path"] == f"/note.{extension}"
    assert result["entry"]["path"] == f"/note.{extension}"
    assert target.read_text(encoding="utf-8") == content


@pytest.mark.asyncio
async def test_write_workspace_file_content_rejects_unsupported_suffix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user = _user()
    root = _workspace_root(user)
    target = root / "script.py"
    target.write_text("print('hello')", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        await svc.write_workspace_file_content(path="/script.py", content="print('bye')", current_user=user)

    assert exc_info.value.status_code == 400
    assert target.read_text(encoding="utf-8") == "print('hello')"


@pytest.mark.asyncio
async def test_write_workspace_file_content_rejects_directory_and_missing_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user = _user()
    workspace_paths.ensure_user_workspace("user-1")

    with pytest.raises(HTTPException) as directory_error:
        await svc.write_workspace_file_content(path="/agents/", content="x", current_user=user)
    with pytest.raises(HTTPException) as missing_error:
        await svc.write_workspace_file_content(path="/missing.md", content="x", current_user=user)

    assert directory_error.value.status_code == 400
    assert missing_error.value.status_code == 404


@pytest.mark.asyncio
async def test_write_workspace_file_content_blocks_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))

    with pytest.raises(HTTPException) as exc_info:
        await svc.write_workspace_file_content(
            path="/../outside.md",
            content="x",
            current_user=_user(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_upload_workspace_files_writes_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user = _user()
    root = _workspace_root(user)
    uploads = [
        UploadFile(filename="demo.txt", file=BytesIO(b"hello")),
        UploadFile(filename="notes.md", file=BytesIO(b"# notes")),
    ]

    previous_umask = os.umask(0o077)
    try:
        result = await svc.upload_workspace_files(parent_path="/", files=uploads, current_user=user)
    finally:
        os.umask(previous_umask)

    assert result["success"] is True
    assert [entry["path"] for entry in result["entries"]] == ["/demo.txt", "/notes.md"]
    assert result["entries"][0]["size"] == 5
    assert (root / "demo.txt").read_bytes() == b"hello"
    assert (root / "notes.md").read_bytes() == b"# notes"
    assert (root / "demo.txt").stat().st_mode & 0o777 == 0o600
    assert (root / "notes.md").stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_create_workspace_directory_uses_owner_only_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))

    previous_umask = os.umask(0o077)
    try:
        result = await svc.create_workspace_directory(
            parent_path="/",
            name="project",
            current_user=_user(),
        )
    finally:
        os.umask(previous_umask)

    target = tmp_path / "threads/shared/user-1/workspace/project"
    assert result["entry"]["path"] == "/project/"
    assert target.stat().st_mode & 0o777 == 0o700


@pytest.mark.asyncio
async def test_upload_workspace_files_rejects_oversized_file_and_cleans_partial_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    monkeypatch.setattr(svc, "MAX_WORKSPACE_UPLOAD_SIZE_BYTES", 5)
    user = _user()
    root = _workspace_root(user)
    uploads = [
        UploadFile(filename="small.txt", file=BytesIO(b"12345")),
        UploadFile(filename="large.txt", file=BytesIO(b"123456")),
    ]

    with pytest.raises(HTTPException) as exc_info:
        await svc.upload_workspace_files(parent_path="/", files=uploads, current_user=user)

    assert exc_info.value.status_code == 400
    assert "100 MB" in exc_info.value.detail
    assert not (root / "small.txt").exists()
    assert not (root / "large.txt").exists()


@pytest.mark.asyncio
async def test_upload_workspace_files_rejects_more_than_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    user = _user()
    uploads = [
        UploadFile(filename=f"demo-{index}.txt", file=BytesIO(b"hello"))
        for index in range(svc.MAX_WORKSPACE_UPLOAD_FILES + 1)
    ]

    with pytest.raises(HTTPException) as exc_info:
        await svc.upload_workspace_files(parent_path="/", files=uploads, current_user=user)

    assert exc_info.value.status_code == 400
    assert f"一次最多上传 {svc.MAX_WORKSPACE_UPLOAD_FILES} 个文件" in exc_info.value.detail


@pytest.mark.asyncio
async def test_search_workspace_files_matches_filenames(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YUXI_USER_DATA_DIR", str(tmp_path / "threads"))
    root = _workspace_root(_user())
    (root / "notes").mkdir(parents=True, exist_ok=True)
    (root / "notes" / "meeting-record.md").write_text("记录", encoding="utf-8")
    (root / "agents" / "MEMORY.md").write_text("记忆", encoding="utf-8")  # 已有默认文件

    response = await svc.search_workspace_files(query="memory", current_user=_user())

    names = [entry["name"] for entry in response["entries"]]
    assert names == ["MEMORY.md"]
    assert response["entries"][0]["path"] == "/agents/MEMORY.md"
    assert response["entries"][0]["virtual_path"] == "/home/gem/user-data/agents/MEMORY.md"

    empty = await svc.search_workspace_files(query="   ", current_user=_user())
    assert empty["entries"] == []


def test_workspace_entry_preserves_v071_virtual_path_contract() -> None:
    metadata = {"is_dir": True, "size": 0, "modified_at": 0}

    root = svc._entry_from_metadata("/", metadata)
    directory = svc._entry_from_metadata("/notes", metadata)

    assert root["virtual_path"] == "/home/gem/user-data"
    assert directory["path"] == "/notes/"
    assert directory["virtual_path"] == "/home/gem/user-data/notes/"
