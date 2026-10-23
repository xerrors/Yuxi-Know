"""引用输出与工具快照的独立边界案例。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.modules.agents.services.references import collect_reference_sources, reference_answer_lines, validate_reference_matches
from yuxi.shared.errors import OperationTimeoutError


def tool(name, payload, *, kb_id="kb-a", message_id=1):
    """构造已完成工具的持久快照。"""
    return SimpleNamespace(
        id=message_id,
        run_id="run-a",
        content="",
        extra_metadata={"tool_name": name, "output": json.dumps(payload, ensure_ascii=False), "input": {"kb_id": kb_id}},
    )


def match(**values):
    """构造严格模型 JSON。"""
    return json.dumps(
        {
            "citations": [
                {
                    "answer_start_line": 1,
                    "answer_end_line": 1,
                    "source_id": "s1",
                    "quote": "证据",
                    **values,
                }
            ]
        },
        ensure_ascii=False,
    )


def test_knowledge_results_keep_resource_identity_and_authoritative_span():
    """标准 query_kb 不依赖知识库名称，重排 chunk 保留原文块范围。"""
    sources = collect_reference_sources(
        [
            tool(
                "query_kb",
                {
                    "kb_id": "kb-a",
                    "results": [
                        {
                            "id": "chunk-g3",
                            "file_id": "file-a",
                            "content": "重排后的证据",
                            "metadata": {"source": "报告.md", "generation": 3, "start_line": 20, "end_line": 29},
                        }
                    ],
                },
            )
        ],
        {"kb-a"},
    )
    assert sources[0]["file_id"] == "file-a"
    assert sources[0]["chunk_id"] == "chunk-g3"
    assert sources[0]["generation"] == 3
    citation = validate_reference_matches(match(), "回答", sources)[0]
    assert (citation["source_start_line"], citation["source_end_line"]) == (20, 29)


def test_numbered_open_window_preserves_empty_lines_and_precise_quote_location():
    """行号剥离不吞空行，摘录位置使用真实窗口起始行。"""
    sources = collect_reference_sources(
        [
            tool(
                "open_kb_document",
                {
                    "kb_id": "kb-a",
                    "file_id": "file-a",
                    "start_line": 10,
                    "end_line": 13,
                    "content": "    10\t标题\n    11\t\n    12\t证据\n    13\t后续",
                },
            )
        ],
        {"kb-a"},
    )
    assert sources[0]["content"] == "标题\n\n证据\n后续"
    citation = validate_reference_matches(match(), "回答", sources)[0]
    assert (citation["source_start_line"], citation["source_end_line"]) == (12, 12)


def test_find_windows_include_parent_file_id():
    """find_kb_document 的窗口继承文件身份。"""
    sources = collect_reference_sources(
        [
            tool(
                "find_kb_document",
                {
                    "file_id": "file-a",
                    "windows": [{"start_line": 7, "end_line": 7, "content": "     7\t证据"}],
                },
            )
        ],
        {"kb-a"},
    )
    assert sources[0]["file_id"] == "file-a"
    assert sources[0]["start_line"] == 7


def test_revoked_knowledge_and_non_retrieval_tools_provide_no_sources():
    """无权来源和普通工具不能进入引用输入。"""
    payload = {"results": [{"content": "证据", "file_id": "file-a"}]}
    assert collect_reference_sources([tool("query_kb", payload)], set()) == []
    assert collect_reference_sources([tool("list_kbs", payload)], {"kb-a"}) == []


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///secret", "https://user:pass@example.org", "http://"])
def test_unsafe_web_addresses_are_not_citable(url):
    """网页链接边界拒绝执行协议和内嵌凭据。"""
    assert collect_reference_sources([tool("web_search", {"results": [{"url": url, "content": "证据"}]})], set()) == []


def test_empty_error_and_duplicate_web_results():
    """只保留有内容的成功网页证据，重复快照合并。"""
    payload = {"results": [{"url": "https://example.org/a", "title": "资料", "content": "证据"}]}
    sources = collect_reference_sources(
        [
            tool("web_search", payload),
            tool("web_search", payload, message_id=2),
            tool("web_search", {"error": "failed", **payload}),
            tool("web_search", {"results": [{"url": "https://example.org/b", "content": ""}]}),
        ],
        set(),
    )
    assert len(sources) == 1
    assert sources[0]["tool_message_id"] == 1


@pytest.mark.parametrize(
    "values",
    [
        {"source_id": "invented"},
        {"quote": "编造摘录"},
        {"quote": " "},
        {"answer_start_line": 0},
        {"answer_end_line": 99},
        {"answer_start_line": 2, "answer_end_line": 1},
        {"answer_start_line": 2, "answer_end_line": 2},
        {"answer_start_line": "1"},
        {"answer_start_line": True},
        {"unexpected": "field"},
    ],
)
def test_invalid_model_matches_fail_for_the_correct_boundary(values):
    """虚构来源、原文和范围不能成为持久引用。"""
    with pytest.raises(ValueError):
        validate_reference_matches(match(**values), "回答\n\n其他回答", [{"id": "s1", "content": "证据"}])


def test_multiple_sources_and_no_evidence_are_valid_results():
    """同一结论允许多个来源，缺乏证据时不强补引用。"""
    raw = json.dumps({"citations": [json.loads(match())["citations"][0], json.loads(match(source_id="s2"))["citations"][0]]})
    sources = [{"id": "s1", "content": "证据"}, {"id": "s2", "content": "其他证据"}]
    assert [item["source_id"] for item in validate_reference_matches(raw, "回答", sources)] == ["s1", "s2"]
    assert validate_reference_matches('{"citations":[]}', "回答", sources) == []


def test_normalized_search_and_fetch_provide_citable_content():
    """新的摘要字段与独立正文工具都进入真实引用来源。"""
    sources = collect_reference_sources(
        [
            tool(
                "web_search",
                {
                    "results": [
                        {"url": "https://example.org/search", "title": "Search", "relevant_content": "相关片段", "raw_content": "正文"}
                    ]
                },
            ),
            tool("web_fetch", {"url": "https://example.org/page", "title": "Fetch", "content": "# 网页正文"}, message_id=2),
        ],
        set(),
    )
    assert [source["content"] for source in sources] == ["相关片段", "# 网页正文"]


def test_reference_input_keeps_original_lines_for_text_images_and_complete_tables():
    """排除内容不发送给标注模型，表格分隔行和过滤后的原始行号保留。"""
    answer = (
        '# 标题\n\n- 正文 `code` 与 $x$。\n\n  ```widget\n  {"type":"Card","children":[]}\n  ```\n\n'
        "![图片](https://example.org/a.png)\n\n| 项目 | 结果 |\n| --- | --- |\n| A | B |\n\n$$\nx^2\n$$\n\n后续"
    )
    lines = reference_answer_lines(answer)
    assert [line["line"] for line in lines] == [3, 9, 11, 12, 13, 19]
    assert [line["text"] for line in lines] == [
        "- 正文 `code` 与 $x$。",
        "![图片](https://example.org/a.png)",
        "| 项目 | 结果 |",
        "| --- | --- |",
        "| A | B |",
        "后续",
    ]
    citations = validate_reference_matches(match(answer_start_line=11, answer_end_line=13), answer, [{"id": "s1", "content": "证据"}])
    assert (citations[0]["answer_start_line"], citations[0]["answer_end_line"]) == (11, 13)


def test_task_list_text_remains_citable():
    """任务列表中的文字属于正文，不因前端生成 checkbox 而丢失标注。"""
    answer = "- [x] 文字结论\n- [ ] 后续结论"
    assert [line["line"] for line in reference_answer_lines(answer)] == [1, 2]
    assert validate_reference_matches(match(answer_end_line=2), answer, [{"id": "s1", "content": "证据"}])[0]["answer_end_line"] == 2


@pytest.mark.parametrize(
    "excluded",
    [
        "```python\nprint(1)\n```",
        '```widget\n{"type":"Card","children":[{"type":"Text","value":"文字"}]}\n```',
        "$$\nx^2\n$$",
        "$$\nx^2",
        "$$x^2$$ $$y^2$$",
        "    code",
        "<div>HTML 预览</div>",
        "仅有 <span>HTML</span>",
        "$x$",
        "`code`",
        "---\nname: metadata\n---",
    ],
)
def test_excluded_answer_types_cannot_be_cited_or_included_in_cross_block_ranges(excluded):
    """合法行号不能绕过内容白名单，包括跨排除内容的范围。"""
    assert reference_answer_lines(excluded) == []
    answer = f"正文\n\n{excluded}\n\n后续"
    sources = [{"id": "s1", "content": "证据"}]
    for start, end in [(3, 3), (1, len(answer.splitlines()))]:
        with pytest.raises(ValueError, match="只能标注"):
            validate_reference_matches(match(answer_start_line=start, answer_end_line=end), answer, sources)


async def test_annotation_timeout_explains_model_configuration_and_keeps_answer_unmodified(monkeypatch):
    """超时保留失败语义与原回答，并给出管理员调整模型的方向。"""
    from yuxi.modules.agents.services import references

    message = SimpleNamespace(content="正文", extra_metadata={"keep": "original"})
    repository = SimpleNamespace(try_lock=AsyncMock(return_value=True))
    monkeypatch.setattr(references, "require_thread", AsyncMock())
    monkeypatch.setattr(references, "TurnReferenceRepository", lambda _db: repository)
    monkeypatch.setattr(
        references,
        "_load_reference_input",
        AsyncMock(return_value=(message, SimpleNamespace(id="run-a"), [{"id": "s1", "content": "证据"}])),
    )
    monkeypatch.setattr(
        references,
        "system_options",
        SimpleNamespace(get=AsyncMock(return_value={"reference_model": "provider:refs", "fast_model": "provider:fast"})),
    )
    monkeypatch.setattr(
        references, "load_chat_model", lambda *_args, **_kwargs: SimpleNamespace(ainvoke=AsyncMock(side_effect=TimeoutError))
    )

    with pytest.raises(OperationTimeoutError, match="设置中选择关闭思考或思考强度较低的来源标注模型") as error:
        await references.annotate_turn_references(
            db=SimpleNamespace(), scope=SimpleNamespace(uid="user-a"), thread_id="thread-a", turn_id="turn-a"
        )

    assert error.value.code == "references_timeout"
    assert message.content == "正文"
    assert message.extra_metadata == {"keep": "original"}
