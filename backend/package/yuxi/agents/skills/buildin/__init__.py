from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from yuxi.agents.toolkits.mysql import get_mysql_tools
from yuxi.agents.toolkits.utils import get_tool_info


@dataclass(frozen=True)
class BuiltinSkillSpec:
    slug: str
    source_dir: Path
    description: str = ""
    version: str = "1.0.0"
    tool_dependencies: tuple[str, ...] = ()
    mcp_dependencies: tuple[str, ...] = ()
    skill_dependencies: tuple[str, ...] = ()


_SKILLS_ROOT = Path(__file__).resolve().parent

BUILTIN_SKILLS: list[BuiltinSkillSpec] = [
    BuiltinSkillSpec(
        slug="deep-reporter",
        source_dir=_SKILLS_ROOT / "deep-reporter",
        description="指导生成科研报告、行业调研和其他需要深度分析的结构化长报告。",
        version="2026.03.28",
        tool_dependencies=["tavily_search"],
    ),
    BuiltinSkillSpec(
        slug="reporter",
        source_dir=_SKILLS_ROOT / "reporter",
        description="生成 SQL 查询报表并生成可视化图表。",
        version="2026.03.28",
        tool_dependencies=[t["name"] for t in get_tool_info(get_mysql_tools())],
        mcp_dependencies=("mcp-server-chart",),
    ),
]
