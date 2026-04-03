import sys


def test_import_yuxi_does_not_eagerly_import_knowledge(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    sys.modules.pop("yuxi", None)
    sys.modules.pop("yuxi.knowledge", None)

    import yuxi

    assert yuxi.get_version() == "0.6.0"
    assert "yuxi.knowledge" not in sys.modules
