from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.support.sqlite import create_utc_sqlite_engine
from yuxi.modules.system.options import ensure_options_in_db, update_option_value
from yuxi.infrastructure.document_parsing.engines import ENGINE_SPECS
import yuxi.modules.documents.service as ocr_service
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.models.tables import ModelProvider


@pytest_asyncio.fixture
async def db_session():
    engine = create_utc_sqlite_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await ensure_options_in_db(session)
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_task_resolution_uses_database_option(db_session):
    await update_option_value(
        db_session,
        "mineru_ocr_host_opts",
        {"server_url": "http://mineru-config:30001"},
        "tester",
    )

    resolved = await ocr_service.resolve_ocr_task_params({"ocr_engine": "mineru_ocr"}, db_session)

    assert resolved["_ocr_processor_kwargs"] == {"server_url": "http://mineru-config:30001/"}


@pytest.mark.asyncio
async def test_ocr_options_use_parser_metadata(db_session, monkeypatch):
    async def get_options(option, _db=None):
        assert option is ocr_service.system_options
        return {"default_ocr_engine": "rapid_ocr"}

    monkeypatch.setattr(type(ocr_service.system_options), "get", get_options)
    options = await ocr_service.get_ocr_options(db_session)

    assert options == {
        "default_engine": "rapid_ocr",
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


@pytest.mark.asyncio
async def test_deepseek_uses_provider_credentials_without_chat_models(db_session):
    provider = ModelProvider(
        provider_id="siliconflow-cn",
        display_name="SiliconFlow",
        provider_type="openai",
        base_url="https://provider.example/v1",
        is_enabled=True,
        api_key="provider-secret",
        api_key_env=None,
        capabilities=["embedding"],
        enabled_models=[{"id": "BAAI/bge-m3", "type": "embedding"}],
    )
    db_session.add(provider)
    await db_session.flush()

    resolved = await ocr_service.resolve_ocr_task_params({"ocr_engine": "deepseek_ocr"}, db_session)

    assert resolved["_ocr_processor_kwargs"] == {
        "api_key": "provider-secret",
        "api_url": "https://provider.example/v1/chat/completions",
    }


@pytest.mark.asyncio
async def test_health_checks_every_registered_ocr_method(db_session, monkeypatch):
    async def build_kwargs(db, engine_id):
        del db
        return {"engine": engine_id}

    monkeypatch.setattr(ocr_service, "_build_processor_kwargs", build_kwargs)
    from types import SimpleNamespace

    monkeypatch.setattr(
        ocr_service,
        "get_engine",
        lambda engine_id, **kwargs: SimpleNamespace(check_health=lambda: {"status": "healthy", "message": kwargs["engine"]}),
    )

    health = await ocr_service.check_all_ocr_health(db_session)

    assert set(health) == set(ENGINE_SPECS)
    assert all(result["status"] == "healthy" for result in health.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_resource_publication_reclaims_failed_or_cancelled_attempt(tmp_path, monkeypatch, cancel):
    """上传线程完成后回收独占前缀，其他文档的资源仍然保留。"""
    import asyncio
    import threading
    from yuxi.infrastructure.document_parsing import ParseResult
    from yuxi.modules.documents import assets

    started, release = threading.Event(), threading.Event()
    objects = {"other-document/image.png": b"other"}

    class Client:
        """模拟不能被 asyncio 取消的实际上传 I/O。"""

        def ensure_bucket_exists(self, bucket):
            pass

        async def aupload_file(self, *, bucket_name, object_name, data):
            def upload():
                if cancel:
                    started.set()
                    assert release.wait(5)
                objects[object_name] = data

            await asyncio.to_thread(upload)

        async def adelete_objects_by_prefix(self, bucket, prefix):
            for name in list(objects):
                if name.startswith(prefix):
                    del objects[name]

    (tmp_path / "image.png").write_bytes(b"image")
    (tmp_path / "document.md").write_text("![](image.png)")
    result = ParseResult(tmp_path, tmp_path / "document.md", ("image.png",))
    monkeypatch.setattr(assets, "get_minio_client", Client)

    def url_builder(name):
        raise ValueError("publication failed")

    task = asyncio.create_task(assets.upload_resources(result, "images", "document/attempt/", url_builder))
    if cancel:
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
    with pytest.raises(asyncio.CancelledError if cancel else ValueError):
        await task
    assert objects == {"other-document/image.png": b"other"}
