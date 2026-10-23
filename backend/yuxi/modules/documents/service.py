"""OCR 方法选择、运行时配置和健康检测。"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.document_parsing import OCR_FILE_EXTENSIONS, ParseOptions, ParseResult
from yuxi.infrastructure.document_parsing.engines import ENGINE_SPECS, get_engine, get_engine_spec
from yuxi.modules.documents.options import (
    mineru_ocr_host_opts,
    mineru_official_api_opts,
    paddleocr_api_opts,
    pp_structure_v3_ocr_host_opts,
)
from yuxi.modules.models.providers.service import resolve_deepseek_ocr_credentials
from yuxi.modules.system.options import system_options


async def get_ocr_options(db: AsyncSession | None = None) -> dict[str, Any]:
    options = await system_options.get(db)
    return {
        "default_engine": options["default_ocr_engine"],
        "engines": [
            {
                "engine_id": engine_id,
                "service_name": capability.service_name,
                "display_name": capability.display_name,
                "supported_extensions": list(capability.supported_extensions),
            }
            for engine_id, capability in ENGINE_SPECS.items()
        ],
    }


def resolve_ocr_engine_id(engine_id: str | None, default_engine: str) -> str:
    resolved = str(engine_id or default_engine).strip() or default_engine
    if resolved == "disable":
        return resolved
    if resolved not in ENGINE_SPECS:
        raise ValueError(f"不支持的 OCR 引擎: {resolved}")
    return resolved


async def resolve_ocr_task_params(
    params: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    resolved = dict(params or {})
    configured_engine = resolved.get("ocr_engine")
    if configured_engine is None:
        default_engine = (await system_options.get(db))["default_ocr_engine"]
    else:
        default_engine = str(configured_engine)
    engine_id = resolve_ocr_engine_id(configured_engine, default_engine)
    resolved["ocr_engine"] = engine_id
    resolved.pop("ocr_engine_config", None)

    if engine_id == "disable":
        kwargs = {}
    elif db is None:
        from yuxi.infrastructure.postgres.manager import pg_manager

        async with pg_manager.get_async_session_context() as session:
            kwargs = await _build_processor_kwargs(session, engine_id)
    else:
        kwargs = await _build_processor_kwargs(db, engine_id)

    resolved["_ocr_processor_kwargs"] = kwargs
    return resolved


async def parse(
    source: str,
    output_dir: str | Path,
    params: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
) -> ParseResult:
    """解析本地或 MinIO 输入，返回完整本地产物，不发布图片。"""
    suffix = Path(source.split("?", 1)[0]).suffix.lower()
    resolved = dict(params or {})
    if suffix in OCR_FILE_EXTENSIONS:
        resolved = await resolve_ocr_task_params(params, db)
        engine_id = resolved["ocr_engine"]
        if engine_id != "disable" and suffix not in get_engine_spec(engine_id).supported_extensions:
            raise ValueError(f"OCR 引擎 {engine_id} 不支持文件类型 {suffix}")
    options = ParseOptions(
        ocr_engine=resolved.pop("ocr_engine", "disable"),
        processor_kwargs=resolved.pop("_ocr_processor_kwargs", {}),
        params=resolved,
    )
    from yuxi.infrastructure.document_parsing.parser import parse as parse_local
    from yuxi.infrastructure.minio.object_urls import is_minio_url, parse_minio_url

    if not is_minio_url(source):
        return await parse_local(source, output_dir, options)
    from yuxi.infrastructure.minio import get_minio_client

    with tempfile.TemporaryDirectory(prefix="yuxi-parse-input-") as directory:
        local_path = Path(directory) / f"source{suffix}"
        bucket, object_name = parse_minio_url(source)
        content = await get_minio_client().adownload_file(bucket, object_name)
        await asyncio.to_thread(local_path.write_bytes, content)
        return await parse_local(local_path, output_dir, options)


async def parse_to_hosted_markdown(
    source: str,
    *,
    image_bucket: str,
    image_prefix: str,
    url_builder: Callable[[str], str],
    params: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
) -> str:
    """解析并发布图片；上传位置与访问 URL 由已授权调用方提供。"""
    from yuxi.modules.documents.assets import upload_resources

    with tempfile.TemporaryDirectory(prefix="yuxi-hosted-markdown-") as directory:
        result = await parse(source, Path(directory) / "parsed", params, db)
        return await upload_resources(result, image_bucket, image_prefix, url_builder)


async def check_all_ocr_health(db: AsyncSession) -> dict[str, Any]:
    """使用当前有效配置并行检查所有 OCR 方法。"""

    configured = []
    results = {}
    for engine_id in ENGINE_SPECS:
        try:
            kwargs = await _build_processor_kwargs(db, engine_id)
            configured.append((engine_id, kwargs))
        except Exception as exc:
            results[engine_id] = {"status": "error", "message": str(exc), "details": {}}

    async def check(engine_id: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        try:
            result = await asyncio.to_thread(get_engine(engine_id, **kwargs).check_health)
        except Exception as exc:
            result = {"status": "error", "message": str(exc), "details": {}}
        return engine_id, result

    checked = await asyncio.gather(*(check(engine_id, kwargs) for engine_id, kwargs in configured))
    results.update(checked)
    return results


async def _build_processor_kwargs(db: AsyncSession, engine_id: str) -> dict[str, Any]:
    if engine_id == "mineru_ocr":
        return await mineru_ocr_host_opts.get(db)
    if engine_id == "mineru_official":
        return await mineru_official_api_opts.get(db)
    if engine_id == "pp_structure_v3_ocr":
        opts = await pp_structure_v3_ocr_host_opts.get(db)
        return {"server_url": opts["server_url"]} if opts["server_url"] else {}
    if engine_id == "deepseek_ocr":
        return await resolve_deepseek_ocr_credentials(db)
    if engine_id in {"paddleocr_vl_1_6", "paddleocr_pp_ocrv6"}:
        opts = await paddleocr_api_opts.get(db)
        return {key: value for key, value in opts.items() if value}
    return {}
