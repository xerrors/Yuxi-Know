from rich.text import Text
from typer.testing import CliRunner

from yuxi_cli import __version__
from yuxi_cli.config import ConfigStore
from yuxi_cli.main import app


def test_version_option_without_command():
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in Text.from_ansi(result.output).plain


def test_agent_eval_help_is_registered():
    result = CliRunner().invoke(app, ["agent", "eval", "--help"])
    output = Text.from_ansi(result.output).plain

    assert result.exit_code == 0
    assert "--dataset-name" in output
    assert "--create-smoke-item" not in output
    assert "--auth-token" not in output


def test_kb_upload_help_is_registered():
    result = CliRunner().invoke(app, ["kb", "upload", "--help"])
    output = Text.from_ansi(result.output).plain

    assert result.exit_code == 0
    assert "--kb-id" in output
    assert "--concurrency" in output
    assert "--force-upload-file" in output
    assert "1-300" in output


def test_chat_command_starts_web_chat(tmp_path, monkeypatch):
    store = ConfigStore(tmp_path / "config.toml")
    config = store.load()
    config.get_remote("local").api_key = "yxkey_test"
    store.save(config)
    calls = []

    def fake_run_web_chat(store_arg, remote, agent_slug, console, *, no_open):
        calls.append((store_arg, remote, agent_slug, console, no_open))

    monkeypatch.setattr("yuxi_cli.main._store", lambda: store)
    monkeypatch.setattr("yuxi_cli.main.run_web_chat", fake_run_web_chat)

    result = CliRunner().invoke(
        app, ["chat", "--agent-slug", "debug-agent", "--no-open"]
    )

    assert result.exit_code == 0
    assert calls[0][0] is store
    assert calls[0][1:3] == (None, "debug-agent")
    assert calls[0][4] is True


def test_remote_command_prints_version_and_remote_context_first(tmp_path, monkeypatch):
    store = ConfigStore(tmp_path / "config.toml")
    config = store.load()
    remote = config.get_remote("local")
    remote.url = "https://example.com"
    store.save(config)

    def fake_remote_ping(store_arg, name, console):
        assert store_arg is store
        assert name is None
        console.print("pong")

    monkeypatch.setattr("yuxi_cli.main._store", lambda: store)
    monkeypatch.setattr("yuxi_cli.main.remote_ping", fake_remote_ping)

    result = CliRunner().invoke(app, ["remote", "ping"])

    assert result.exit_code == 0
    output = Text.from_ansi(result.output).plain
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    assert lines[:3] == [f"Yuxi CLI {__version__}", "Remote: local https://example.com", "pong"]
