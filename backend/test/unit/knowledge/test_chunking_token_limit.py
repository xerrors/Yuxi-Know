"""验证分块 token 上限、内容完整性及输入顺序。"""

import pytest

from yuxi.modules.knowledge.chunking.ragflow_like import nlp
from yuxi.modules.knowledge.chunking.ragflow_like.parsers import general

# ── nlp.hard_split_by_token_limit ──────────────────────────────────


class TestHardSplitByTokenLimit:
    @pytest.mark.parametrize("text", ["这是一段短文本", "，。！？"])
    def test_short_text_unchanged(self, text):
        result = nlp.hard_split_by_token_limit(text, 512)
        assert result == [text]

    def test_splits_long_chinese_text(self):
        text = "甲乙丙丁戊己庚辛壬癸" * 120
        result = nlp.hard_split_by_token_limit(text, 512)
        assert len(result) > 1
        assert "".join("".join(result).split()) == "".join(text.split())
        for chunk in result:
            assert nlp.count_tokens(chunk) <= 512

    def test_optional_hard_limit_keeps_slightly_oversized_text(self):
        text = "内容" * 300  # 600 CJK tokens
        result = nlp.hard_split_by_token_limit(text, 512, hard_limit_token_num=768)
        assert result == [text]

    def test_optional_hard_limit_merges_short_tail(self):
        text = "内容" * 635  # 1270 CJK tokens -> 512 + 512 + 246
        result = nlp.hard_split_by_token_limit(text, 512, hard_limit_token_num=768)
        assert len(result) == 2
        assert "".join(result) == text
        assert [nlp.count_tokens(chunk) for chunk in result] == [512, 758]

    def test_splits_long_english_text(self):
        text = "alpha beta gamma delta " * 500  # ~2000 word tokens
        result = nlp.hard_split_by_token_limit(text, 512)
        assert len(result) > 1
        assert "".join("".join(result).split()) == "".join(text.split())
        for chunk in result:
            assert nlp.count_tokens(chunk) <= 512

    def test_empty_text_returns_empty(self):
        assert nlp.hard_split_by_token_limit("", 512) == []

    def test_whitespace_only_returns_empty(self):
        assert nlp.hard_split_by_token_limit("   \n\t  ", 512) == []

    def test_zero_limit_floors_to_one(self):
        text = "a b c"  # 3 个独立 token（单词）
        result = nlp.hard_split_by_token_limit(text, 0)
        # max_tokens = max(0, 1) = 1, 每个 token 单独一个 chunk
        assert result == ["a", "b", "c"]


# ── general._ensure_chunk_token_limit ──────────────────────────────


class TestEnsureChunkTokenLimit:
    @pytest.mark.parametrize(
        "chunks",
        [
            ["短文本一", "短文本二", "短文本三"],
            ["短文本", "内容" * 300, "短文本二"],
        ],
    )
    def test_chunks_within_limit_pass_through(self, chunks):
        result = general._ensure_chunk_token_limit(chunks, 512)
        assert result == chunks

    def test_oversized_chunk_gets_split_with_merged_tail(self):
        long_text = "内容" * 635  # 1270 CJK tokens -> 512 + 758
        chunks = ["短文本", long_text, "短文本二"]
        result = general._ensure_chunk_token_limit(chunks, 512)
        assert result[0] == "短文本"
        assert result[-1] == "短文本二"
        assert "".join(result) == "".join(chunks)
        middle_chunks = result[1:-1]
        assert len(middle_chunks) == 2
        assert [nlp.count_tokens(chunk) for chunk in middle_chunks] == [512, 758]

    def test_empty_chunks_filtered(self):
        chunks = ["有效文本", "", "   ", "另一段"]
        result = general._ensure_chunk_token_limit(chunks, 512)
        assert result == ["有效文本", "另一段"]

    def test_zero_limit_returns_stripped(self):
        chunks = ["  文本一  ", "文本二"]
        result = general._ensure_chunk_token_limit(chunks, 0)
        assert result == ["文本一", "文本二"]


# ── general.chunk_markdown 集成 ────────────────────────────────────


class TestGeneralChunkMarkdown:
    def test_normal_document_chunks_within_limit(self):
        doc = "# 标题\n\n第一段内容\n\n第二段内容\n\n第三段内容"
        chunks = general.chunk_markdown(doc, {"chunk_token_num": 512})
        assert len(chunks) > 0
        assert "".join("".join(chunks).split()) == "".join(doc.split())
        for chunk in chunks:
            assert nlp.count_tokens(chunk) <= 512

    def test_oversized_single_line_gets_split(self):
        long_line = "甲乙丙丁戊己庚辛壬癸" * 320  # ~3200 CJK tokens
        doc = f"# 运维知识库\n\n{long_line}"
        chunks = general.chunk_markdown(doc, {"chunk_token_num": 512})
        assert len(chunks) > 1
        assert "".join("".join(chunks).split()) == "".join(doc.split())
        for chunk in chunks:
            assert nlp.count_tokens(chunk) <= 768

    def test_empty_document_returns_empty(self):
        assert general.chunk_markdown("", {"chunk_token_num": 512}) == []

    def test_default_config_uses_512(self):
        doc = "测试\n" * 400  # 约 800 token；默认值错误放宽到 1024 时不会切分
        chunks = general.chunk_markdown(doc)
        token_counts = [nlp.count_tokens(chunk) for chunk in chunks]
        assert token_counts == [514, 286]
