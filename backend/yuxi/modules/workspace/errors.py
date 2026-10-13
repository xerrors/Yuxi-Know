"""Workspace 文件边界使用的传输异常。"""

from yuxi.infrastructure.filesystem import FileTransferLimitError

__all__ = ["FileTransferLimitError", "ProjectHasPendingAgentWorkError"]


class ProjectHasPendingAgentWorkError(Exception):
    """Project 内仍有不能归档的执行或输入。"""
