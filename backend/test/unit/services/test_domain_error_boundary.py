"""领域异常的协议独立性与幂等拒绝契约。"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuxi.modules.agents.services import inputs, turns
from yuxi.modules.workspace.services import projects
from yuxi.shared.errors import DomainError, StateConflictError

pytestmark = pytest.mark.unit


def test_domain_modules_do_not_depend_on_http_exceptions():
    """领域源码不导入或消费 HTTP 异常及框架状态常量。"""
    root = Path(__file__).resolve().parents[3] / "yuxi"
    violations = []
    for path in [root / "shared/errors.py", *sorted((root / "modules").rglob("*.py"))]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            framework_import = isinstance(node, ast.ImportFrom) and node.module in {"fastapi", "starlette.exceptions", "starlette.status"}
            exception_reference = (
                isinstance(node, (ast.Name, ast.Attribute)) and (node.id if isinstance(node, ast.Name) else node.attr) == "HTTPException"
            )
            if framework_import or exception_reference:
                violations.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not violations, f"领域包含 HTTP 依赖: {violations}"


@pytest.mark.parametrize("owner", ["inputs", "turns", "projects"])
def test_idempotency_rejection_is_a_protocol_free_conflict(owner):
    """异意图重放供 HTTP 与 worker 消费同一领域冲突类型。"""
    with pytest.raises(StateConflictError) as caught:
        if owner == "inputs":
            inputs.require_input_replay(SimpleNamespace(event_type="message", intent_hash="old"), "message", "new")
        elif owner == "turns":
            turns._require_replay(SimpleNamespace(event_type="cancel", intent_hash="old"), "cancel", "new")
        else:
            projects._require_matching_creation_intent(
                SimpleNamespace(status="active", name="old", directory_mode="linked", workdir_path="projects/test"),
                name="new",
                workdir_path="projects/test",
            )
    error = caught.value
    assert isinstance(error, DomainError)
    assert str(error) == error.message
    assert not hasattr(error, "status_code")
    assert not hasattr(error, "detail")
