"""QA parser 的结构化提取与超长 chunk 限长回归测试。

验收主张：围栏内的 Q:/A: 或标题行属于答案正文；`chunk_markdown` 产出的任意
单条 chunk 不超过 embedding 上限，且切分时保留完整问答语义。
"""

import importlib.util
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[3]


def _load_qa_parser():
    """按文件路径隔离加载 qa parser；其仅依赖标准库，无需注册 sys.modules。"""
    spec = importlib.util.spec_from_file_location(
        "qa_parser_under_test",
        _PKG / "yuxi/modules/knowledge/chunking/ragflow_like/parsers/qa.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


qa = _load_qa_parser()

# embedding 上下文上限的保守字符兜底（对应 bge_m3 4096 token），独立于实现常量以避免自我引用 oracle
_EMBEDDING_CHAR_LIMIT = 4000
_QUESTION = "问题：" + "这是一个问题" * 5  # 远低于上限，切分后可原样保留


def _long_chunk(answer_body: str) -> str:
    return f"{_QUESTION}\t回答：{answer_body}"


def _split(chunks: list[str]) -> list[str]:
    """显式传入限长值，单测只验证切分逻辑本身，不依赖实现默认常量。"""
    return qa._split_long_qa_chunks(chunks, max_chars=_EMBEDDING_CHAR_LIMIT)


class TestSplitLongQaChunks:
    def test_short_chunks_pass_through(self):
        chunks = ["问题：短问题\t回答：短答案", "Question: q\tAnswer: a"]
        assert _split(chunks) == [c.strip() for c in chunks]

    def test_blank_chunks_filtered(self):
        assert _split(["", "   ", "问题：q\t回答：a"]) == ["问题：q\t回答：a"]

    def test_long_answer_split_by_paragraphs_keeps_question(self):
        body = "\n\n".join(f"段落{i}内容。" * 300 for i in range(3))
        result = _split([_long_chunk(body)])
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= _EMBEDDING_CHAR_LIMIT
            # 每条子 chunk 保留完整问题与前缀，维持问答语义
            assert chunk.startswith(f"{_QUESTION}\t回答：")
        # 答案内容在切分结果中完整保留
        joined = "".join(c.split("\t回答：", 1)[1] for c in result)
        for i in range(3):
            assert f"段落{i}内容。" in joined

    def test_single_long_paragraph_falls_back_to_lines(self):
        body = "\n".join(f"第{i}行" + "内容" * 100 for i in range(30))
        result = _split([_long_chunk(body)])
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= _EMBEDDING_CHAR_LIMIT
            assert chunk.startswith(f"{_QUESTION}\t回答：")

    def test_line_split_preserves_code_indentation(self):
        # 缩进对围栏代码块有语义：按行切分不得剥离前导空白
        code = ["```python", "def handler():", "    if ready:", "        return compute()", "```"]
        filler = [f"说明行{i}：" + "内容" * 100 for i in range(30)]
        body = "\n".join(filler[:15] + code + filler[15:])
        result = _split([_long_chunk(body)])
        assert len(result) > 1
        joined = "\n".join(result)
        for line in code:
            assert line in joined

    def test_structureless_long_answer_hard_split(self):
        result = _split([_long_chunk("答" * 9000)])
        assert len(result) >= 3
        for chunk in result:
            assert len(chunk) <= _EMBEDDING_CHAR_LIMIT
            assert chunk.startswith(f"{_QUESTION}\t回答：")

    def test_oversized_question_falls_back_to_hard_split(self):
        # 问题本身已接近上限时，保留问题切答案只会产出 1 字符答案碎片，应整条硬切
        chunk = "问题：" + "超" * 5000 + "\t回答：答案"
        result = _split([chunk])
        assert len(result) > 1
        assert all(len(c) <= _EMBEDDING_CHAR_LIMIT for c in result)

    def test_non_standard_chunk_hard_split(self):
        result = _split(["无结构文本" * 1000])
        assert len(result) > 1
        assert all(len(c) <= _EMBEDDING_CHAR_LIMIT for c in result)

    def test_question_containing_tab_kept_whole(self):
        # 问题本身含 tab：结构分隔符是紧邻答案前缀的 tab，不是首个任意 tab
        question = "问题：什么是\t缩进风格？"
        result = _split([question + "\t回答：" + "答案内容。" * 1500])
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= _EMBEDDING_CHAR_LIMIT
            assert chunk.startswith(question + "\t回答：")

    def test_question_marker_from_other_language_is_not_separator(self):
        # 英文序列化只能由 Answer 分隔；问题正文中的中文回答标记属于问题内容
        question = "Question: how is\t回答： represented?"
        result = _split([question + "\tAnswer: " + "long answer. " * 800])
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= _EMBEDDING_CHAR_LIMIT
            assert chunk.startswith(question + "\tAnswer: ")

    def test_tab_chunk_without_answer_marker_hard_split(self):
        # 含 tab 但无已知答案前缀的 chunk 仍属非标准格式，硬切兜底
        result = _split(["左列\t右列" * 1000])
        assert len(result) > 1
        assert all(len(c) <= _EMBEDDING_CHAR_LIMIT for c in result)

    def test_zero_max_chars_only_strips(self):
        assert qa._split_long_qa_chunks(["  问题：q\t回答：a  "], max_chars=0) == ["问题：q\t回答：a"]


class TestChunkMarkdownLengthCap:
    """端到端验收：真实 QA 文档经 chunk_markdown 后任意 chunk 不超 embedding 上限。"""

    _LONG_MD = "Q: 高频问题\nA: " + "长答案内容。" * 1500

    def test_all_chunks_within_embedding_limit(self):
        # 走实现默认常量：锁定「默认上限不超 embedding 承诺」这一工程主张，_QA_CHUNK_MAX_CHARS 被调过 4000 时本断言失败
        chunks = qa.chunk_markdown("faq.md", self._LONG_MD)
        assert len(chunks) > 1
        assert all(len(c) <= _EMBEDDING_CHAR_LIMIT for c in chunks)
        assert all(c.startswith("问题：高频问题\t回答：") for c in chunks)


_TILDE_MD = "Q: 如何配置？\nA: 参考示例：\n~~~\nQ: 注释里的文本\nA: 不是真实问答\n~~~\n完成后重启。"


class TestPrefixFenceBoundary:
    @pytest.mark.parametrize("fence", ["~~~", "```"])
    def test_fence_content_stays_in_answer(self, fence):
        # 围栏内的 Q:/A: 行不得拆出虚构问答对。
        pairs = qa._extract_pairs_by_prefix(_TILDE_MD.replace("~~~", fence))
        assert len(pairs) == 1
        q, a = pairs[0]
        assert q == "如何配置？"
        assert "注释里的文本" in a
        assert "完成后重启。" in a

    def test_fence_with_info_string(self):
        md = "Q: 配置？\nA: 示例：\n~~~python\nQ: 注释\n~~~\n完。"
        pairs = qa._extract_pairs_by_prefix(md)
        assert len(pairs) == 1
        assert "Q: 注释" in pairs[0][1]

    def test_mismatched_fence_does_not_close_block(self):
        # ``` 行不关闭 ~~~ 块；块内 Q: 行仍属答案
        md = "Q: 配置？\nA: 开始\n~~~\n```\nQ: 仍在块内\n~~~\nQ: 真实问题2\nA: 答案2"
        pairs = qa._extract_pairs_by_prefix(md)
        assert len(pairs) == 2
        assert "仍在块内" in pairs[0][1]
        assert pairs[1] == ("真实问题2", "答案2")

    def test_unclosed_fence_absorbs_rest_into_answer(self):
        md = "Q: 配置？\nA: 开始\n~~~\nQ: 后面全在块内\nA: 也是"
        pairs = qa._extract_pairs_by_prefix(md)
        assert len(pairs) == 1
        assert "后面全在块内" in pairs[0][1]

    def test_heading_inside_tilde_fence_not_treated_as_question(self):
        # 标题提取路径：tilde 块内的 # 行不识别为标题
        md = "# 安装\n步骤一\n~~~\n# 注释不是标题\n~~~\n步骤二"
        pairs = qa._extract_pairs_from_markdown_headings(md)
        assert len(pairs) == 1
        q, a = pairs[0]
        assert q == "安装"
        assert "注释不是标题" in a
        assert "步骤二" in a

    def test_chunk_markdown_end_to_end_tilde_fence(self):
        chunks = qa.chunk_markdown("faq.md", _TILDE_MD)
        assert len(chunks) == 1
        assert chunks[0].startswith("问题：如何配置？\t回答：")
        assert "注释里的文本" in chunks[0]


class TestAtxHeadingBoundary:
    """只有合法 ATX 标题才能结束问答，井号代码行必须保留。"""

    def test_prefix_answer_keeps_hash_prefixed_code(self):
        md = 'Q: 如何输出？\nA: 使用标准库：\n#include <stdio.h>\nprintf("hi");'

        pairs = qa._extract_pairs_by_prefix(md)

        assert pairs == [("如何输出？", '使用标准库：\n#include <stdio.h>\nprintf("hi");')]

    def test_heading_answer_keeps_hash_prefixed_code(self):
        md = '# 如何输出？\n使用标准库：\n#include <stdio.h>\nprintf("hi");'

        pairs = qa._extract_pairs_from_markdown_headings(md)

        assert pairs == [("如何输出？", '使用标准库：\n#include <stdio.h>\nprintf("hi");')]


class TestOrphanAnswer:
    """答案前缀行必须归属活跃问题，孤儿答案不得污染后续问答对。"""

    def test_orphan_answer_before_first_question_discarded(self):
        md = "Answer: 孤儿前言\n# Q: 真实问题\nA: 真实答案"
        pairs = qa._extract_pairs_by_prefix(md)
        assert pairs == [("真实问题", "真实答案")]

    def test_orphan_answer_between_pairs_discarded(self):
        # 上一对已结束（分节标题 flush）、新问题未出现时，孤儿答案同样忽略
        md = "Q: 问题一\nA: 答案一\n# 分节\nA: 孤儿\nQ: 问题二\nA: 答案二"
        pairs = qa._extract_pairs_by_prefix(md)
        assert pairs == [("问题一", "答案一"), ("问题二", "答案二")]

    def test_multiple_answer_lines_within_question_kept(self):
        # 活跃问题下的多个 A: 行仍全部归入答案（修复不改变正常路径）
        md = "Q: 问题\nA: 第一行\nA: 第二行"
        pairs = qa._extract_pairs_by_prefix(md)
        assert pairs == [("问题", "第一行\n第二行")]
