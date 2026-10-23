import pytest

from yuxi.modules.knowledge.utils.kb_utils import (
    build_kb_image_proxy_url,
    prepare_item_metadata,
    resolve_processing_params,
    sanitize_processing_params,
)


def test_build_kb_image_proxy_url_uses_private_bucket_proxy_path():
    url = build_kb_image_proxy_url("db_1/kb-images/1710000000000_diagram.png")

    assert url == "/api/knowledge/knowledge-bases/db_1/images/kb-images/1710000000000_diagram.png"


def test_build_kb_image_proxy_url_encodes_special_chars_but_keeps_slashes():
    url = build_kb_image_proxy_url("db_1/kb-images/1710000000000_user 1.png")

    assert url == "/api/knowledge/knowledge-bases/db_1/images/kb-images/1710000000000_user%201.png"


@pytest.mark.parametrize("object_name", ["db_1/images/a.png", "/kb-images/a.png", "db_1"])
def test_build_kb_image_proxy_url_rejects_invalid_object_name(object_name):
    with pytest.raises(ValueError, match="知识库图片对象名"):
        build_kb_image_proxy_url(object_name)


async def test_prepare_item_metadata_preserves_uploaded_file_size():
    item = "minio://knowledgebases/db/upload/demo.txt"
    params = {
        "content_hashes": {item: "hash"},
        "file_sizes": {item: 1234},
    }

    metadata = await prepare_item_metadata(item, "file", "db", params=params)

    assert metadata["size"] == 1234
    assert "file_sizes" not in (metadata.get("processing_params") or {})


async def test_prepare_item_metadata_keeps_leaf_and_leaves_directory_to_import_service():
    item = "minio://knowledgebases/db/upload/intro_1710000000000.md"
    params = {
        "content_hashes": {item: "hash"},
        "source_path": "guides/setup/Intro.MD",
    }

    metadata = await prepare_item_metadata(item, "file", "db", params=params)

    assert metadata["filename"] == "intro_1710000000000.md"
    assert metadata["file_type"] == "md"
    assert metadata["path"] == item


async def test_prepare_item_metadata_preserves_preprocessed_file_size():
    item = "minio://knowledgebases/db/upload/page.html"
    params = {
        "_preprocessed_map": {
            item: {
                "path": item,
                "content_hash": "hash",
                "filename": "https://example.com",
                "file_size": 5678,
            }
        }
    }

    metadata = await prepare_item_metadata(item, "file", "db", params=params)

    assert metadata["size"] == 5678
    assert "_preprocessed_map" not in (metadata.get("processing_params") or {})


async def test_prepare_item_metadata_rejects_direct_url_content_type():
    with pytest.raises(ValueError, match="Unsupported content_type"):
        await prepare_item_metadata("https://example.com", "url", "db")


def test_sanitize_processing_params_should_drop_non_persistent_fields() -> None:
    sanitized = sanitize_processing_params(
        {
            "chunk_preset_id": "general",
            "chunk_parser_config": {"chunk_token_num": 300},
            "ocr_engine": "mineru_ocr",
            "ocr_engine_config": {},
            "auto_index": True,
            "content_hashes": {"a.md": "hash-a"},
            "enable_ocr": "mineru_ocr",
            "_preprocessed_map": {"a.md": {"path": "/tmp/a.md"}},
        }
    )

    assert sanitized == {
        "chunk_preset_id": "general",
        "chunk_parser_config": {"chunk_token_num": 300},
        "ocr_engine": "mineru_ocr",
    }


def test_resolve_processing_params_keeps_ocr_fields_and_chunk_params() -> None:
    resolved = resolve_processing_params(
        kb_additional_params={
            "chunk_preset_id": "book",
            "chunk_parser_config": {"delimiter": "\n", "chunk_token_num": 300},
        },
        file_processing_params={
            "ocr_engine": "mineru_ocr",
            "ocr_engine_config": {"backend": "pipeline"},
            "chunk_preset_id": "qa",
            "chunk_parser_config": {"overlapped_percent": 10},
            "content_hashes": {"a.md": "hash-a"},
        },
        request_params={
            "auto_index": True,
            "chunk_preset_id": "laws",
            "chunk_parser_config": {"chunk_token_num": 666},
        },
    )

    assert resolved["ocr_engine"] == "mineru_ocr"
    assert "ocr_engine_config" not in resolved
    assert resolved["chunk_preset_id"] == "laws"
    assert resolved["chunk_parser_config"] == {
        "delimiter": "\n",
        "chunk_token_num": 666,
        "overlapped_percent": 10,
    }
    assert "content_hashes" not in resolved
    assert "enable_ocr" not in resolved
    assert "auto_index" not in resolved


def test_resolve_processing_params_does_not_inject_runtime_defaults() -> None:
    resolved = resolve_processing_params(
        kb_additional_params={},
        file_processing_params={"ocr_engine_config": "invalid", "enable_ocr": "mineru_ocr"},
    )

    assert "ocr_engine" not in resolved
    assert "ocr_engine_config" not in resolved
    assert "enable_ocr" not in resolved


def test_resolve_processing_params_drops_file_and_request_ocr_config() -> None:
    resolved = resolve_processing_params(
        kb_additional_params={},
        file_processing_params={
            "ocr_engine": "rapid_ocr",
            "ocr_engine_config": {"det_box_thresh": 0.4, "zoom_x": 3.0},
        },
        request_params={"ocr_engine_config": {"det_box_thresh": 0.6}},
    )

    assert resolved["ocr_engine"] == "rapid_ocr"
    assert "ocr_engine_config" not in resolved
