from __future__ import annotations

import pytest


from types import SimpleNamespace
from unittest.mock import AsyncMock

from yuxi.modules.knowledge.graphs.extractors import GraphExtractorFactory, LLMGraphExtractor
from yuxi.modules.knowledge.graphs.milvus_graph_service import MilvusGraphService

pytestmark = pytest.mark.usefixtures("milvus_graph_projection_lock")


def test_llm_graph_extractor_rejects_custom_prompt():
    extractor = LLMGraphExtractor({"model_spec": "test/model", "prompt": "custom"})

    with pytest.raises(ValueError, match="不支持自定义完整 Prompt"):
        extractor.validate_options()


def test_llm_graph_extractor_defaults_extraction_timeout():
    """不配置时保持历史默认值，避免改变既有部署的行为。"""
    extractor = LLMGraphExtractor({"model_spec": "test/model"})

    assert extractor._resolve_timeout_seconds() == 60.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("timeout_options", "text", "expected_timeout"),
    [
        pytest.param({"timeout_seconds": 300}, "某型发动机的涵道比设计值为 9.0", 300.0, id="configured"),
        pytest.param({}, "文本", 60.0, id="default"),
    ],
)
async def test_llm_graph_extractor_passes_resolved_timeout_to_model(
    monkeypatch,
    timeout_options,
    text,
    expected_timeout,
):
    """配置超时和默认超时都必须传入模型调用。"""
    captured = {}

    class FakeModel:
        async def call(self, prompt, stream=False):
            return SimpleNamespace(content='{"relations": []}')

    def fake_select_model(**kwargs):
        captured.update(kwargs)
        return FakeModel()

    monkeypatch.setattr("yuxi.modules.knowledge.graphs.extractors.llm.select_model", fake_select_model)
    extractor = LLMGraphExtractor({"model_spec": "test/model", **timeout_options})

    await extractor.extract(text)

    assert captured["timeout"] == expected_timeout
    assert captured["model_spec"] == "test/model"


@pytest.mark.parametrize("value", [300, "300", 600, 0.5])
def test_llm_graph_extractor_accepts_valid_timeout(value):
    """上界 600 与字符串数字都应当被接受（字符串数字与既有 concurrency_count 风格一致）。"""
    extractor = LLMGraphExtractor({"model_spec": "test/model", "timeout_seconds": value})

    extractor.validate_options()

    assert extractor._resolve_timeout_seconds() == float(value)


@pytest.mark.parametrize(
    "bad_value",
    [
        0,
        -1,
        600.0001,
        "abc",
        None,
        "",  # 空字符串
        True,  # bool 是 int 子类，float(True)==1.0 会被区间校验放行
        False,
        float("nan"),  # NaN 让区间比较全部为 False
        "NaN",
        float("inf"),
        10**400,  # 超大整数在 float() 上抛 OverflowError
    ],
    ids=[
        "zero",
        "negative",
        "above_max",
        "text",
        "null",
        "empty",
        "true",
        "false",
        "nan",
        "nan_str",
        "inf",
        "huge_int",
    ],
)
def test_llm_graph_extractor_rejects_invalid_timeout(bad_value):
    """越界、非数字、非有限值与布尔要显式失败。

    这几类如果被静默放行，会变成「配置保存成功、构建时整库全挂」：bool 会配出 1 秒超时，
    NaN/inf 会让每次调用直接报错，超大整数则会在路由兜底分支变成 500 而非 400。
    """
    extractor = LLMGraphExtractor({"model_spec": "test/model", "timeout_seconds": bad_value})

    with pytest.raises(ValueError, match="timeout_seconds"):
        extractor.validate_options()


def test_llm_graph_extractor_rejects_top_level_enable_thinking():
    """顶层 enable_thinking 会被当成 create() 的未知参数，保存配置时就要报错。"""
    extractor = LLMGraphExtractor({"model_spec": "test/model", "model_params": {"enable_thinking": False}})

    with pytest.raises(ValueError, match="extra_body"):
        extractor.validate_options()


def test_llm_graph_extractor_accepts_enable_thinking_in_extra_body():
    extractor = LLMGraphExtractor({"model_spec": "test/model", "model_params": {"extra_body": {"enable_thinking": False}}})

    extractor.validate_options()


def test_llm_graph_extractor_appends_schema_to_fixed_prompt():
    extractor = LLMGraphExtractor(
        {
            "model_spec": "test/model",
            "schema": "实体类型只能是 Person 或 Organization",
            "concurrency_count": 5,
            "model_params": {"temperature": 0.1},
        }
    )

    prompt = extractor._build_prompt("张三任职于公司")

    assert "请从下面文本中抽取实体和实体关系" in prompt
    assert "抽取 Schema 约束" in prompt
    assert "实体类型只能是 Person 或 Organization" in prompt
    assert "文本：\n张三任职于公司" in prompt


def test_graph_extractor_factory_supports_only_llm_and_rejects_spacy():
    with pytest.raises(ValueError, match="spacy"):
        GraphExtractorFactory.create("spacy", {"model": "zh_core_web_sm"})


@pytest.mark.asyncio
async def test_graph_extraction_retries_twice_before_third_attempt_succeeds(monkeypatch):
    chunk = SimpleNamespace(
        chunk_id="chunk_1",
        file_id="file_1",
        chunk_index=0,
        content="张三任职于公司",
        extraction_result=None,
        graph_extraction_details={"status": "failed", "attempt_count": 3},
    )
    extractor = SimpleNamespace(
        extractor_type="llm",
        extract=AsyncMock(
            side_effect=[
                RuntimeError("timeout"),
                ValueError("invalid json"),
                {"entities": [], "relations": []},
            ]
        ),
    )
    chunk_repo = SimpleNamespace(
        mark_graph_extraction_pending=AsyncMock(),
        mark_graph_extraction_failed=AsyncMock(),
        update_extraction_result=AsyncMock(),
    )
    service = MilvusGraphService(chunk_repo=chunk_repo)
    monkeypatch.setattr(
        "yuxi.modules.knowledge.graphs.milvus_graph_service.GRAPH_EXTRACTION_RETRY_DELAYS_SECONDS",
        (0, 0),
    )

    result = await service._get_chunk_extraction_result("kb_test", chunk, extractor)

    assert result["metadata"]["extractor_type"] == "llm"
    assert extractor.extract.await_count == 3
    chunk_repo.mark_graph_extraction_pending.assert_awaited_once_with("chunk_1")
    chunk_repo.update_extraction_result.assert_awaited_once_with("chunk_1", result, 3)
    chunk_repo.mark_graph_extraction_failed.assert_not_awaited()
