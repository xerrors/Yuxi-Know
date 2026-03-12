from types import SimpleNamespace

import pytest

from src.config.app import config
from src.sandbox.base import Sandbox
from src.sandbox.k8s_sandbox import K8sSandbox, K8sSandboxProvider
from src.sandbox.provider import get_sandbox_provider, reset_sandbox_provider
from src.sandbox.provisioner_client import ProvisionedSandbox


@pytest.fixture(autouse=True)
def _reset_sandbox_provider():
    reset_sandbox_provider()
    original_mode = config.sandbox_mode
    original_provisioner_url = config.sandbox_k8s_provisioner_url
    original_timeout = config.sandbox_k8s_request_timeout_seconds
    config.sandbox_mode = "local"
    config.sandbox_k8s_provisioner_url = ""
    config.sandbox_k8s_request_timeout_seconds = 30.0
    yield
    config.sandbox_mode = original_mode
    config.sandbox_k8s_provisioner_url = original_provisioner_url
    config.sandbox_k8s_request_timeout_seconds = original_timeout
    reset_sandbox_provider()


def test_sandbox_execute_command():
    provider = get_sandbox_provider()
    sandbox = provider.acquire("test_exec")
    assert isinstance(sandbox, Sandbox)

    output = sandbox.execute_command("echo Hello Sandbox")
    assert "Hello Sandbox" in output


def test_sandbox_file_read_write():
    provider = get_sandbox_provider()
    sandbox = provider.acquire("test_file")

    sandbox.write_file("test.txt", "hello")
    assert sandbox.read_file("test.txt") == "hello"

    sandbox.write_file("test.txt", " world", append=True)
    assert sandbox.read_file("test.txt") == "hello world"


def test_sandbox_list_dir():
    provider = get_sandbox_provider()
    sandbox = provider.acquire("test_ls")

    sandbox.write_file("a.txt", "aaa")
    sandbox.write_file("sub/b.txt", "bbb")

    entries = sandbox.list_dir("/")
    text = "\n".join(entries)
    assert "a.txt" in text
    assert "sub" in text


def test_sandbox_release():
    provider = get_sandbox_provider()
    provider.acquire("test_release")
    assert provider.get("test_release") is not None

    provider.release("test_release")
    assert provider.get("test_release") is None


def test_get_sandbox_provider_returns_k8s_provider(monkeypatch):
    config.sandbox_mode = "k8s"
    config.sandbox_k8s_provisioner_url = "http://provisioner:8002"

    monkeypatch.setattr(
        "src.sandbox.k8s_sandbox.ProvisionerClient",
        lambda base_url, timeout_seconds: SimpleNamespace(),
    )

    provider = get_sandbox_provider()
    assert isinstance(provider, K8sSandboxProvider)


def test_k8s_provider_acquire_uses_cache(monkeypatch):
    config.sandbox_k8s_provisioner_url = "http://provisioner:8002"

    provision_calls = []

    class FakeProvisionerClient:
        def __init__(self, base_url: str, timeout_seconds: float):
            self.base_url = base_url
            self.timeout_seconds = timeout_seconds

        def create_sandbox(self, sandbox_id: str) -> ProvisionedSandbox:
            provision_calls.append(sandbox_id)
            return ProvisionedSandbox(sandbox_id=sandbox_id, base_url=f"http://runtime/{sandbox_id}")

        def delete_sandbox(self, sandbox_id: str) -> None:
            pass

    monkeypatch.setattr("src.sandbox.k8s_sandbox.ProvisionerClient", FakeProvisionerClient)

    provider = K8sSandboxProvider()
    first = provider.acquire("thread-1")
    second = provider.acquire("thread-1")

    assert first is second
    assert provision_calls == ["thread-1"]


def test_k8s_provider_release_deletes_and_clears_cache(monkeypatch):
    config.sandbox_k8s_provisioner_url = "http://provisioner:8002"

    deleted = []

    class FakeProvisionerClient:
        def __init__(self, base_url: str, timeout_seconds: float):
            self.base_url = base_url
            self.timeout_seconds = timeout_seconds

        def create_sandbox(self, sandbox_id: str) -> ProvisionedSandbox:
            return ProvisionedSandbox(sandbox_id=sandbox_id, base_url=f"http://runtime/{sandbox_id}")

        def delete_sandbox(self, sandbox_id: str) -> None:
            deleted.append(sandbox_id)

    monkeypatch.setattr("src.sandbox.k8s_sandbox.ProvisionerClient", FakeProvisionerClient)

    provider = K8sSandboxProvider()
    provider.acquire("thread-2")

    assert provider.get("thread-2") is not None
    provider.release("thread-2")

    assert deleted == ["thread-2"]
    assert provider.get("thread-2") is None


def test_k8s_sandbox_maps_remote_responses():
    class FakeRemoteClient:
        def execute_command(self, command: str, cwd: str = "/workspace") -> dict:
            assert command == "python main.py"
            assert cwd == "/workspace"
            return {"stdout": "ok", "stderr": "warn", "exit_code": 2}

        def read_file(self, path: str) -> dict:
            assert path == "/workspace/demo.txt"
            return {"content": "hello"}

        def write_file(self, path: str, content: str, append: bool = False) -> dict:
            assert path == "/workspace/demo.txt"
            assert content == "hello"
            assert append is True
            return {"ok": True}

        def list_dir(self, path: str) -> dict:
            assert path == "/workspace"
            return {"entries": ["📄 demo.txt", "📁 sub"]}

    sandbox = K8sSandbox("thread-3", "http://runtime/thread-3", FakeRemoteClient())

    assert sandbox.execute_command("python main.py") == "ok\nStd Error:\nwarn\nExit Code: 2"
    assert sandbox.read_file("demo.txt") == "hello"
    sandbox.write_file("demo.txt", "hello", append=True)
    assert sandbox.list_dir("/workspace") == ["📄 demo.txt", "📁 sub"]
