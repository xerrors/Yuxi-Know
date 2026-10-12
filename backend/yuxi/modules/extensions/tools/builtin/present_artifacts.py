"""登记当前用户可见的交付物。"""

from typing import Annotated, Literal

from langchain.tools import InjectedToolCallId
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.types import Command
from pydantic import BaseModel, Field

from yuxi.modules.agents.runtime.sandbox.paths import normalize_artifact_path
from yuxi.modules.extensions.tools.builtin.sandbox_scope import resolve_runtime_sandbox_scope
from yuxi.modules.extensions.tools.registry import tool


class PresentArtifactsInput(BaseModel):
    """声明交付物文件路径。"""

    filepaths: list[str] = Field(description="需要展示给用户的文件绝对路径列表")
    type: Literal["file", "image"] = Field(default="file", description="展示类型：file 为文件卡片，image 为 300px 宽图片预览")


PRESENT_ARTIFACTS_DESCRIPTION = """
将已经生成好的结果文件展示给用户。

使用场景：
1. 你已经在合适的位置写好了最终结果文件
2. 你希望前端在对话结束后显示这些结果文件卡片
3. 这些文件需要支持下载或预览

注意事项：
1. 可以传入当前 Project Workdir、User Data 或已授权 Skills 中的普通文件
2. 不要传入中间过程文件，只有真正需要给用户看的结果文件才调用
3. 可以一次传多个文件
4. type 默认为 file；需要直接展示图片内容时指定 image，同一次调用的文件使用相同类型
5. 图片与文件都属于交付物，混合交付时分别按 type 调用
"""


@tool(
    category="builtin",
    tags=["文件", "交付物"],
    display_name="展示交付物",
    description=PRESENT_ARTIFACTS_DESCRIPTION,
    args_schema=PresentArtifactsInput,
)
def present_artifacts(
    filepaths: list[str],
    runtime: ToolRuntime,
    tool_call_id: Annotated[str, InjectedToolCallId],
    type: Literal["file", "image"] = "file",
) -> Command:
    """登记当前用户可见的普通文件，使前端展示给用户。"""
    try:
        normalized_paths = [_normalize_presented_artifact_path(filepath, runtime) for filepath in filepaths]
    except ValueError as exc:
        return Command(update={"messages": [ToolMessage(content=f"Error: {exc}", tool_call_id=tool_call_id, status="error")]})

    return Command(
        update={
            "artifacts": [{"path": path, "type": type} for path in normalized_paths],
            "messages": [ToolMessage(content="已将交付物展示给用户", tool_call_id=tool_call_id)],
        }
    )


def _normalize_presented_artifact_path(filepath: str, runtime: ToolRuntime) -> str:
    """校验交付物属于当前用户可见的普通文件。"""
    from yuxi.modules.agents.runtime.sandbox.backend import ProvisionerSandboxBackend

    runtime_context = runtime.context
    runtime_scope_id, uid, workdir_relative_path = resolve_runtime_sandbox_scope(runtime)

    normalized_path = normalize_artifact_path(getattr(runtime_context, "workdir_path", None), filepath)
    backend = ProvisionerSandboxBackend(
        thread_id=runtime_scope_id,
        uid=str(uid),
        workdir_path=workdir_relative_path,
        create_if_missing=True,
    )
    if not backend.regular_file_exists(normalized_path):
        raise ValueError(f"文件不存在或不是普通文件: {filepath}")
    return normalized_path
