from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml


def project_root() -> Path:
    """定位当前工作树的 Compose 根目录。"""
    configured = os.environ.get("YUXI_PROJECT_ROOT")
    if configured:
        return Path(configured)

    for parent in Path(__file__).resolve().parents:
        if (parent / "docker-compose.yml").exists():
            return parent
    pytest.skip("当前测试环境未挂载仓库根目录")


def load_compose(filename: str = "docker-compose.yml") -> dict:
    """读取未插值的 Compose 配置。"""
    return yaml.safe_load((project_root() / filename).read_text())
