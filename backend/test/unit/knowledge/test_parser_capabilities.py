from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from yuxi.infrastructure.document_parsing import (
    IMAGE_FILE_EXTENSIONS,
    SUPPORTED_FILE_EXTENSIONS,
    is_supported_file_extension,
)
from yuxi.infrastructure.document_parsing.engines import ENGINE_SPECS, get_ocr_engines_for_extension

pytestmark = pytest.mark.unit


def test_capability_metadata_covers_upload_and_ocr_formats() -> None:
    assert ".webp" in IMAGE_FILE_EXTENSIONS
    assert ".webp" in SUPPORTED_FILE_EXTENSIONS
    assert ".doc" not in SUPPORTED_FILE_EXTENSIONS
    assert ".ppt" not in SUPPORTED_FILE_EXTENSIONS
    assert get_ocr_engines_for_extension("webp") == ("deepseek_ocr",)
    assert get_ocr_engines_for_extension("docx") == ("mineru_official",)
    assert get_ocr_engines_for_extension("ppt") == ()
    assert is_supported_file_extension("report.PPTX")
    assert not is_supported_file_extension("legacy.doc")


def test_capability_lookup_does_not_load_concrete_parser_modules() -> None:
    package_dir = Path(__file__).resolve().parents[3]
    script = f"""
import sys
sys.path.insert(0, {str(package_dir)!r})
from yuxi.infrastructure.document_parsing.engines import get_engine_spec

get_engine_spec("rapid_ocr")
assert "yuxi.infrastructure.document_parsing.engines.rapid_ocr" not in sys.modules
assert "docling" not in sys.modules
"""

    subprocess.run([sys.executable, "-c", script], check=True)


def test_knowledge_router_import_does_not_load_docling_or_ocr_provider() -> None:
    backend_dir = Path(__file__).resolve().parents[3]
    script = f"""
import sys
sys.path.insert(0, {str(backend_dir)!r})
import yuxi.api.routers.knowledge

assert "docling" not in sys.modules
assert "yuxi.infrastructure.document_parsing.engines.rapid_ocr" not in sys.modules
assert "yuxi.infrastructure.document_parsing.engines.mineru" not in sys.modules
"""

    subprocess.run([sys.executable, "-c", script], check=True)


@pytest.mark.asyncio
async def test_parse_document_rejects_ocr_engine_without_format_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yuxi.modules.documents.service as ocr_service

    source = tmp_path / "scan.webp"
    source.write_bytes(b"not an image")

    async def _resolve_rapid_ocr(*args, **kwargs) -> dict[str, str]:
        del args, kwargs
        return {"ocr_engine": "rapid_ocr"}

    monkeypatch.setattr(ocr_service, "resolve_ocr_task_params", _resolve_rapid_ocr)

    with pytest.raises(ValueError, match=r"不支持文件类型 \.webp"):
        await ocr_service.parse(str(source), tmp_path / "parsed", params={"ocr_engine": "rapid_ocr"})


def test_capability_registry_declares_shipping_processors() -> None:
    assert tuple(ENGINE_SPECS) == (
        "rapid_ocr",
        "mineru_ocr",
        "mineru_official",
        "pp_structure_v3_ocr",
        "deepseek_ocr",
        "paddleocr_vl_1_6",
        "paddleocr_pp_ocrv6",
    )


def test_concurrent_engine_configuration_returns_each_requested_instance(monkeypatch):
    """共享缓存被另一配置替换时，每个调用仍返回自己请求的引擎。"""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace

    from yuxi.infrastructure.document_parsing import engines

    first_written, second_finished = Event(), Event()

    class ConfiguredEngine:
        """保留构造配置，作为返回实例的独立断言依据。"""

        def __init__(self, server_url):
            self.server_url = server_url

    class Cache(dict):
        """在第一次发布实例后固定交错顺序。"""

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            if value[1].server_url == "https://first.example.test":
                first_written.set()
                assert second_finished.wait(5)

    monkeypatch.setattr(engines, "_ENGINE_CACHE", Cache())
    spec = engines.get_engine_spec("mineru_ocr")
    monkeypatch.setattr(engines, "import_module", lambda _module: SimpleNamespace(**{spec.class_name: ConfiguredEngine}))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(engines.get_engine, "mineru_ocr", server_url="https://first.example.test")
        try:
            assert first_written.wait(5)
            second = pool.submit(engines.get_engine, "mineru_ocr", server_url="https://second.example.test").result(5)
        finally:
            second_finished.set()
        assert first.result(5).server_url == "https://first.example.test"
        assert second.server_url == "https://second.example.test"
