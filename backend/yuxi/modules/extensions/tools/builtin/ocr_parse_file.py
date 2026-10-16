"""解析沙盒文件并保存 Markdown 产物。"""

import asyncio
import re
import tempfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field

from yuxi.infrastructure.filesystem import await_io
from yuxi.modules.agents.runtime.sandbox import UserSandboxBackend
from yuxi.modules.extensions.tools.builtin.file_context import resolve_file_context, runtime_context_value
from yuxi.modules.extensions.tools.registry import tool
from yuxi.modules.system.options import system_options
from yuxi.modules.workspace.filesystem import Workspace
from yuxi.modules.workspace.runtime_paths import SHARED_SKILLS_PATH, WORKSPACE_PATH, runtime_workdir_path
from yuxi.modules.workspace.workdir import Workdir

_OCR_OUTPUT_DIR_NAME = "ocr"
_OCR_PREVIEW_LIMIT = 1200
_SAFE_OUTPUT_STEM_RE = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")


class OcrParseFileInput(BaseModel):
    """声明 OCR 输入文件和可选引擎。"""

    file_path: str = Field(description="需要 OCR 解析的 Project、User Data 或已授权 Skill 文件绝对路径")
    ocr_engine: str | None = Field(default=None, description="可选 OCR 引擎；省略时使用系统默认 OCR 引擎")


OCR_PARSE_FILE_DESCRIPTION = """
将沙盒中的 PDF、Office 文档或图片文件解析为 Markdown 文本，并把结果保存为文件。

使用场景：
1. 用户上传了 PDF、Office 文档或图片附件，需要提取其中的文字内容
2. Project Workdir、User Data 或 Skills 下已有文件，需要转成可读取的 Markdown
3. 解析结果较长，后续应使用 read_file 读取保存后的 Markdown 文件

注意事项：
1. file_path 必须位于当前用户可见范围
2. 解析结果会写入当前 Project Workdir 的 outputs/ocr/ 下
4. 工具只返回结果文件路径和短预览，不直接返回完整 OCR 文本
5. 如需在前端展示结果文件，请再调用 present_artifacts
"""


@tool(
    category="builtin",
    tags=["文件", "OCR"],
    display_name="OCR 解析文件",
    description=OCR_PARSE_FILE_DESCRIPTION,
    args_schema=OcrParseFileInput,
)
async def ocr_parse_file(file_path: str, runtime: ToolRuntime, ocr_engine: str | None = None) -> dict:
    """解析文件并整体保存到当前 Workdir，返回入口路径与短预览。"""
    from yuxi.modules.documents.service import parse

    uid, workdir_relative_path = resolve_file_context(runtime)
    source_virtual_path = _resolve_ocr_source_path(file_path, runtime)
    backend = UserSandboxBackend(
        uid=uid,
        workdir_path=workdir_relative_path,
    )
    from yuxi.modules.documents.service import resolve_ocr_engine_id

    engine = resolve_ocr_engine_id(ocr_engine, (await system_options.get())["default_ocr_engine"])
    with tempfile.TemporaryDirectory(prefix="yuxi-ocr-") as directory:
        suffix = PurePosixPath(source_virtual_path).suffix
        source_temp = f"{directory}/source{suffix}"
        try:
            await await_io(
                asyncio.to_thread(
                    backend.download_authorized_file_to_path,
                    source_virtual_path,
                    source_temp,
                    100 * 1024 * 1024,
                )
            )
        except ValueError as exc:
            raise ValueError(f"文件不存在或不是普通文件: {source_virtual_path}") from exc
        result = await parse(source_temp, Path(directory) / "parsed", params={"ocr_engine": engine})
        base_name = _safe_ocr_output_stem(PurePosixPath(source_virtual_path))
        output_directory = f"/outputs/{_OCR_OUTPUT_DIR_NAME}/{base_name}_{uuid4().hex}"
        workdir = Workdir(workdir_relative_path, Workspace(uid))
        parsed_path = f"{runtime_workdir_path(workdir_relative_path)}{output_directory}/document.md"
        markdown = await await_io(asyncio.to_thread(result.markdown_path.read_text, encoding="utf-8"))
        preview, truncated = _ocr_preview(markdown)
        await workdir.acopy_directory_from_path(result.directory, output_directory)

    return {
        "source_path": source_virtual_path,
        "parsed_path": parsed_path,
        "ocr_engine": engine,
        "char_count": len(markdown),
        "preview": preview,
        "truncated": truncated,
    }


def _resolve_ocr_source_path(file_path: str, runtime: ToolRuntime) -> str:
    """校验 OCR 输入位于当前用户可见文件范围。"""
    resolve_file_context(runtime)

    normalized_input = str(file_path or "").strip()
    if not normalized_input:
        raise ValueError("文件路径不能为空")
    if ".." in PurePosixPath(normalized_input).parts:
        raise ValueError("只允许解析当前用户可见范围内的文件")

    clean_virtual_path = "/" + normalized_input.lstrip("/")
    workdir_path = str(runtime_context_value(runtime, "workdir_path") or "").rstrip("/")
    allowed = clean_virtual_path.startswith(f"{workdir_path}/") or clean_virtual_path.startswith(f"{WORKSPACE_PATH.rstrip('/')}/")
    allowed = allowed or clean_virtual_path.startswith(f"{SHARED_SKILLS_PATH}/")
    if not workdir_path or not allowed:
        raise ValueError("只允许解析当前用户可见范围内的文件")

    return clean_virtual_path


def _safe_ocr_output_stem(source_path: Path) -> str:
    """从源文件名生成安全的输出名称。"""
    stem = source_path.stem.strip() or "ocr_result"
    safe_stem = _SAFE_OUTPUT_STEM_RE.sub("_", stem).strip("._-")
    return safe_stem or "ocr_result"


def _ocr_preview(markdown: str) -> tuple[str, bool]:
    """返回短预览及截断状态。"""
    if len(markdown) <= _OCR_PREVIEW_LIMIT:
        return markdown, False
    return markdown[:_OCR_PREVIEW_LIMIT].rstrip(), True
