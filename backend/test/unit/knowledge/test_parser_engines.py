from __future__ import annotations

import pytest

import re
from pathlib import Path

from yuxi.infrastructure.document_parsing import DocumentParserException
from yuxi.infrastructure.document_parsing.engines.mineru import MinerUParser
from yuxi.infrastructure.document_parsing.engines.mineru_official import MinerUOfficialParser
from yuxi.infrastructure.document_parsing.engines.rapid_ocr import RapidOCRParser


def test_mineru_parser_normalizes_trailing_slash():
    parser = MinerUParser(server_url="http://mineru-api:30001/")

    assert parser.server_url == "http://mineru-api:30001"
    assert parser.parse_endpoint == "http://mineru-api:30001/file_parse"


def test_mineru_official_health_check_does_not_create_task(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "yuxi.infrastructure.document_parsing.engines.mineru_official.requests.post",
        lambda *args, **kwargs: pytest.fail("健康检查不应创建解析任务"),
    )

    health = MinerUOfficialParser(api_key="test-key").check_health()

    assert health["status"] == "configured"


def test_mineru_official_parsing_uses_shared_zip_processor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    file_path = tmp_path / "mineru.pdf"
    file_path.write_bytes(b"pdf")
    zip_path = tmp_path / "result.zip"
    zip_path.write_bytes(b"zip")
    parser = MinerUOfficialParser(api_key="test-key")

    monkeypatch.setattr(parser, "_upload_file", lambda *args, **kwargs: "batch-id")
    monkeypatch.setattr(
        parser,
        "_poll_batch_result",
        lambda *args, **kwargs: {"state": "done", "full_zip_url": "https://example.test/result.zip"},
    )
    monkeypatch.setattr(parser, "_download_zip", lambda *args, **kwargs: str(zip_path))
    processed_paths: list[str] = []

    def _process_zip_file(zip_file_path: str, output_dir: Path, **kwargs) -> str:
        del kwargs
        processed_paths.append(zip_file_path)
        return "parsed markdown"

    monkeypatch.setattr(
        "yuxi.infrastructure.document_parsing.engines.mineru_official.extract_markdown_archive",
        _process_zip_file,
    )

    assert parser.process_file(str(file_path), tmp_path) == "parsed markdown"
    assert processed_paths == [str(zip_path)]
    assert not zip_path.exists()


def test_mineru_official_does_not_fallback_when_shared_zip_processing_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    file_path = tmp_path / "mineru.pdf"
    file_path.write_bytes(b"pdf")
    zip_path = tmp_path / "result.zip"
    zip_path.write_bytes(b"zip")
    parser = MinerUOfficialParser(api_key="test-key")

    monkeypatch.setattr(parser, "_upload_file", lambda *args, **kwargs: "batch-id")
    monkeypatch.setattr(
        parser,
        "_poll_batch_result",
        lambda *args, **kwargs: {"state": "done", "full_zip_url": "https://example.test/result.zip"},
    )
    monkeypatch.setattr(parser, "_download_zip", lambda *args, **kwargs: str(zip_path))

    def _raise_zip_processing_error(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("malformed result archive")

    monkeypatch.setattr(
        "yuxi.infrastructure.document_parsing.engines.mineru_official.extract_markdown_archive",
        _raise_zip_processing_error,
    )

    with pytest.raises(DocumentParserException, match="malformed result archive"):
        parser.process_file(str(file_path), tmp_path)

    assert not zip_path.exists()


def test_rapid_ocr_health_check_does_not_load_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "yuxi.infrastructure.document_parsing.engines.rapid_ocr.RapidOCR",
        lambda *args, **kwargs: pytest.fail("健康检查不应加载 OCR 模型"),
    )

    health = RapidOCRParser().check_health()

    assert health["status"] == "healthy"


def test_lock_excludes_full_docling_and_torch_runtime() -> None:
    lock_text = (Path(__file__).parents[3] / "uv.lock").read_text(encoding="utf-8")
    package_names = set(re.findall(r'^name = "([^"]+)"$', lock_text, flags=re.MULTILINE))

    assert {
        "docling",
        "docling-ibm-models",
        "docling-parse",
        "torch",
        "torchvision",
    }.isdisjoint(package_names)


def test_rapid_ocr_resolves_model_dir_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target_dir = tmp_path / "custom_models"
    monkeypatch.setenv("RAPIDOCR_MODEL_DIR", str(target_dir))
    parser = RapidOCRParser()
    params = parser._get_model_params()

    assert params["Global.model_root_dir"] == str(target_dir)
    assert target_dir.exists()
