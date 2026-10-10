from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yuxi.services.task_service import TaskContext

TaskHandler = Callable[["TaskContext"], Awaitable[object]]
TaskSuccessHandler = Callable[[object, object, object], Awaitable[None]]
TaskFailureHandler = Callable[[object, object, str], Awaitable[None]]


@dataclass(frozen=True)
class TaskDefinition:
    """描述可持久重建的任务 Handler。"""

    task_type: str
    module: str
    function: str
    success_function: str | None = None
    failure_function: str | None = None
    version: int = 1

    def load_handler(self) -> TaskHandler:
        return self._load(self.function, "handler")

    def load_success_handler(self) -> TaskSuccessHandler | None:
        return self._load(self.success_function, "success handler") if self.success_function is not None else None

    def load_failure_handler(self) -> TaskFailureHandler | None:
        return self._load(self.failure_function, "failure handler") if self.failure_function is not None else None

    def _load(self, function: str, label: str):
        """惰性加载并校验一个注册 Handler。"""
        handler = getattr(import_module(self.module), function)
        if not callable(handler):
            raise TypeError(f"Task {label} is not callable: {self.module}:{function}")
        return handler


_TASK_DEFINITIONS = {
    definition.task_type: definition
    for definition in (
        TaskDefinition(
            "knowledge_ingest",
            "yuxi.services.knowledge_task_service",
            "run_knowledge_ingest",
            failure_function="fail_knowledge_file_task",
        ),
        TaskDefinition(
            "knowledge_preview",
            "yuxi.services.knowledge_preview_service",
            "run_knowledge_preview",
        ),
        TaskDefinition(
            "knowledge_parse",
            "yuxi.services.knowledge_task_service",
            "run_knowledge_parse",
            failure_function="fail_knowledge_file_task",
        ),
        TaskDefinition(
            "knowledge_index",
            "yuxi.services.knowledge_task_service",
            "run_knowledge_index",
            failure_function="fail_knowledge_file_task",
        ),
        TaskDefinition(
            "knowledge_graph_index",
            "yuxi.services.knowledge_task_service",
            "run_knowledge_graph",
        ),
        TaskDefinition(
            "knowledge_virtual_folder_migration",
            "yuxi.services.knowledge_task_service",
            "run_virtual_folder_migration",
        ),
        TaskDefinition(
            "dataset_generation",
            "yuxi.knowledge.eval.service",
            "run_dataset_generation_task",
            success_function="finish_dataset_generation_task",
            failure_function="fail_dataset_generation_task",
        ),
        TaskDefinition(
            "rag_evaluation",
            "yuxi.knowledge.eval.service",
            "run_rag_evaluation_task",
            success_function="finish_rag_evaluation_task",
            failure_function="fail_rag_evaluation_task",
        ),
    )
}


def get_task_definition(task_type: str, handler_version: int = 1) -> TaskDefinition:
    """返回当前 shipping TaskDefinition，并拒绝未知类型或版本。"""
    definition = _TASK_DEFINITIONS.get(task_type)
    if definition is None:
        raise ValueError(f"Unknown task type: {task_type}")
    if definition.version != handler_version:
        raise ValueError(
            f"Unsupported handler version for {task_type}: {handler_version}; expected {definition.version}"
        )
    return definition


def get_failure_task_definition(task_type: str, handler_version: int) -> TaskDefinition:
    """只为迁移生成的 legacy v0 复用当前 failure hook。"""
    if handler_version == 0:
        return get_task_definition(task_type)
    return get_task_definition(task_type, handler_version)
