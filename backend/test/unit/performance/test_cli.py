"""统一入口的路径、预算与离线产物契约。"""

import importlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from test.performance import matrix
from test.performance.__main__ import build_parser, main


def test_parser_preserves_matrix_budget_and_requires_command():
    """CLI 默认分组与矩阵一致，且必须显式选择子命令。"""
    args = build_parser().parse_args(["matrix", "--output-dir", "unused"])
    assert args.workers == [1, 4, 8]
    assert args.concurrency == [1, 10, 20, 50, 100]
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args([])
    assert error.value.code == 2


def test_module_help_from_repository_and_backend_roots():
    """宿主机仓库入口与容器中的后端包都能发现同一套命令。"""
    backend = Path(__file__).resolve().parents[3]
    # 容器只挂载 backend；仓库根模式由宿主机执行同一测试覆盖。
    locations = [(backend, "test.performance")]
    if (backend.parent / "docker-compose.yml").is_file():
        locations.append((backend.parent, "backend.test.performance"))
    for directory, module in locations:
        for arguments in (["--help"], ["matrix", "--help"], ["load", "--help"], ["report", "--help"]):
            result = subprocess.run(
                [sys.executable, "-m", module, *arguments],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, result.stderr
            assert "usage:" in result.stdout


def test_compose_probe_targets_resolve():
    """从实际覆盖文件读取 API 工厂与 Worker 适配器，防止迁移后仍引用旧包。"""
    directory = Path(matrix.__file__).parent
    compose = yaml.safe_load((directory / "compose.yml").read_text())
    target = compose["services"]["api"]["command"].split()[1]
    module, factory = target.split(":")
    assert callable(getattr(importlib.import_module(module), factory))
    worker_module = compose["services"]["worker"]["command"].split()[-1]
    assert callable(importlib.import_module(worker_module).run)
    assert (matrix.ROOT / matrix.compose_args()[-1]).resolve() == directory / "compose.yml"
    if (directory.parents[2] / "docker-compose.yml").is_file():
        assert matrix.ROOT == directory.parents[2]


def test_report_writes_both_outputs_without_external_access(tmp_path):
    """通过实际文件验证阶段计算和报告，不调用 Docker、认证或模型。"""
    request = {
        "run_id": "r",
        "api_received_ns": 0,
        "model_send_ns": 8_000_000,
        "success": True,
        "db": {"status": "completed", "attempts": 1, "bound_output": True},
        "api_spans": [],
        "spans": [
            {"name": name, "start_ns": start * 1_000_000, "end_ns": (start + 1) * 1_000_000}
            for name, start in (
                ("run_worker.persist_run_manifest", 2),
                ("ChatbotAgent.get_graph", 4),
                ("AsyncPostgresSaver.aget_tuple", 6),
            )
        ],
        **{metric: 8 for metric in matrix.summarize_timings([])},
    }
    data = {
        "groups": [
            {
                "workers": 1,
                "concurrency": 1,
                "planned_requests": 1,
                "p95_ms": 8,
                "successful_rps": 1,
                "requests": [request],
                "events": [{"event": "model_send", "run_id": "r", "start_ns": 1_000_000}],
            }
        ]
    }
    path = tmp_path / "matrix.json"
    original = json.dumps(data)
    path.write_text(original)
    with patch("test.performance.matrix.command", side_effect=AssertionError("离线报告访问容器")):
        assert main(["report", str(path)]) == 0
    assert path.read_text() == original
    phases = json.loads((tmp_path / "stages.json").read_text())[0]["phase_percentiles"]
    assert len(phases) == 8
    assert all(value == {"p50": 1.0, "p95": 1.0} for value in phases.values())
    assert "| 1 | 1 | 1/1 | 1 | 8 / 8 (n=1) | 完整 |" in (tmp_path / "report.md").read_text()


def test_report_duplicate_groups_preserves_all_outputs(tmp_path):
    """拒绝重复组时，统一入口不能先覆盖报告或阶段结果。"""
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps({"groups": [{"workers": 1, "concurrency": 10}] * 2}))
    for name in ("stages.json", "report.md"):
        (tmp_path / name).write_text("previous\n")
    with pytest.raises(ValueError, match="重复"):
        main(["report", str(path), "--refresh"])
    for name in ("stages.json", "report.md"):
        assert (tmp_path / name).read_text() == "previous\n"
    assert not (tmp_path / "complete.json").exists()


def test_report_preserves_failed_samples_and_actual_rounds(tmp_path):
    """模型前失败不能中断报告，也不能把小实验写成正式预算。"""
    path = tmp_path / "matrix.json"
    path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "workers": 1,
                        "concurrency": 10,
                        "rounds_per_thread": 2,
                        "planned_requests": 20,
                        "successful_rps": 0,
                        "requests": [{"success": False, "run_id": None}],
                        "observation_error": "RuntimeError",
                    }
                ]
            }
        )
    )
    assert main(["report", str(path)]) == 0
    stages = json.loads((tmp_path / "stages.json").read_text())[0]
    assert stages["critical_phases"] == {}
    assert stages["phase_error"] == "缺少模型发送或关键阶段探针"
    report = (tmp_path / "report.md").read_text()
    assert "| 1 | 10 | 1/20 | 0 | None / None (n=0) | 不完整；RuntimeError |" in report
    assert "阶段统计不可用" in report
    assert "Worker 1 / 并发 10：2 轮" in report
    assert "100/10/5/5/5" not in report
