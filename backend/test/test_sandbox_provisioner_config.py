from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_NAME = "sandbox_provisioner_app_for_test"


def _find_module_path() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "docker" / "sandbox_provisioner" / "app.py"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("docker/sandbox_provisioner/app.py not found from test path")


MODULE_PATH = _find_module_path()


def _load_module():
    existing = sys.modules.get(MODULE_NAME)
    if existing is not None:
        return existing

    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_canonical_backend_name_maps_local_to_docker(monkeypatch):
    monkeypatch.setenv("PROVISIONER_BACKEND", "memory")
    module = _load_module()

    assert module.canonical_backend_name("local") == "docker"
    assert module.canonical_backend_name("docker") == "docker"
    assert module.canonical_backend_name("kubernetes") == "kubernetes"


def test_build_backend_keeps_local_compatible_but_returns_docker_name(monkeypatch):
    monkeypatch.setenv("PROVISIONER_BACKEND", "local")
    module = _load_module()

    sentinel = object()
    monkeypatch.setattr(module, "LocalContainerProvisionerBackend", lambda: sentinel)

    backend_impl, backend_name = module._build_backend()

    assert backend_impl is sentinel
    assert backend_name == "docker"
