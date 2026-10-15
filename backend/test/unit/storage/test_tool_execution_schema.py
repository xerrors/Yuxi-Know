"""工具执行事实的持久化边界。"""

from yuxi.bootstrap.models import load_models


def test_tool_execution_has_no_independent_legacy_table():
    """恢复旧 ORM 会重新建立第二份工具事实，必须直接失败。"""
    business, _ = load_models()
    assert "messages" in business.tables
    assert "tool_calls" not in business.tables
