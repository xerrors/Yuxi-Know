"""真实 PostgreSQL 文本协议证明解析正文已消除 NUL 持久化缺陷。"""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from yuxi.infrastructure.document_parsing.parser import parse

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def test_parsed_text_round_trips_through_postgres_and_raw_null_is_rejected(
    tmp_path: Path, postgres_sessions
) -> None:
    """负控恢复真实驱动拒绝原因，归一化结果保留其余字符并往返一致。"""
    original = "完整开头\x00完整结尾\n第二行"
    source = tmp_path / "source.txt"
    source.write_bytes(original.encode())
    result = await parse(source, tmp_path / "parsed")
    content = result.markdown_path.read_text()

    async with postgres_sessions() as session:
        with pytest.raises(DBAPIError, match="invalid byte sequence|NUL|0x00"):
            await session.scalar(text("SELECT CAST(:value AS TEXT)"), {"value": original})
        await session.rollback()
        assert await session.scalar(text("SELECT CAST(:value AS TEXT)"), {"value": content}) == "完整开头�完整结尾\n第二行"

    assert source.read_bytes() == original.encode()
