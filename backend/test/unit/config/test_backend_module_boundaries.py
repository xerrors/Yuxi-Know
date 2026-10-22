"""后端分层边界的静态依赖方向。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "yuxi"


@pytest.mark.parametrize(
    ("relative_path", "forbidden"),
    [
        ("infrastructure/oidc/client.py", ("yuxi.modules",)),
        ("migrations/main.py", ("yuxi.bootstrap",)),
        ("migrations/schema.py", ("yuxi.bootstrap",)),
        ("modules/system/options.py", ("yuxi.modules.extensions",)),
    ],
)
def test_layering_edges_do_not_regress(relative_path: str, forbidden: tuple[str, ...]) -> None:
    imports = _imports(relative_path)

    _assert_no_forbidden_imports(imports, forbidden)
    for module in forbidden:
        with pytest.raises(AssertionError, match=module):
            _assert_no_forbidden_imports(imports | {module}, forbidden)


def test_orm_registry_is_owned_by_persistence_layer() -> None:
    """Schema 初始化不得反向依赖组合根。"""
    assert (PACKAGE_ROOT / "infrastructure/postgres/models.py").is_file()
    assert not (PACKAGE_ROOT / "bootstrap/models.py").exists()


def _imports(relative_path: str) -> set[str]:
    tree = ast.parse((PACKAGE_ROOT / relative_path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _assert_no_forbidden_imports(imports: set[str], forbidden: tuple[str, ...]) -> None:
    for module in imports:
        assert not module.startswith(forbidden), f"forbidden import: {module}"
