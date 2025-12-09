import asyncio
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Awaitable, Callable
from collections import Counter

from src.config import config
from src.utils.logging_config import logger
from src.utils.datetime_utils import utc_isoformat

TaskCoroutine = Callable[["TaskContext"], Awaitable[Any]]
TERMINAL_STATUSES = {"success", "failed", "cancelled"}


def _utc_timestamp() -> str:
    return utc_isoformat()


@dataclass
class Task:
    id: str
    name: str
    type: str
    status: str = "pending"
    progress: float = 0.0
    message: str = ""
    created_at: str = field(default_factory=_utc_timestamp)
    updated_at: str = field(default_factory=_utc_timestamp)
    started_at: str | None = None
    completed_at: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    result: Any | None = None
    error: str | None = None
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    def to_summary_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("payload", None)
        data.pop("result", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            id=data["id"],
            name=data.get("name", "Unnamed Task"),
            type=data.get("type", "general"),
            status=data.get("status", "pending"),
            progress=data.get("progress", 0.0),
            message=data.get("message", ""),
            created_at=data.get("created_at", _utc_timestamp()),
            updated_at=data.get("updated_at", _utc_timestamp()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            payload=data.get("payload", {}),
            result=data.get("result"),
            error=data.get("error"),
            cancel_requested=data.get("cancel_requested", False),
        )


class TaskContext:
    def __init__(self, tasker: "Tasker", task_id: str):
        self._tasker = tasker
        self.task_id = task_id

    async def set_progress(self, progress: float, message: str | None = None) -> None:
        await self._tasker._update_task(
            self.task_id,
            progress=max(0.0, min(progress, 100.0)),
            message=message,
        )

    async def set_message(self, message: str) -> None:
        await self._tasker._update_task(self.task_id, message=message)

    async def set_result(self, result: Any) -> None:
        await self._tasker._update_task(self.task_id, result=result)

    def is_cancel_requested(self) -> bool:
        return self._tasker._is_cancel_requested(self.task_id)

    async def raise_if_cancelled(self) -> None:
        if self.is_cancel_requested():
            raise asyncio.CancelledError("Task was cancelled")


class Tasker:
    def __init__(self, worker_count: int = 2):
        self.worker_count = max(1, worker_count)
        self._queue: asyncio.Queue[tuple[str, TaskCoroutine]] = asyncio.Queue()
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._workers: list[asyncio.Task[Any]] = []
        self._storage_path = Path(config.save_dir) / "tasks" / "tasks.json"
        os.makedirs(self._storage_path.parent, exist_ok=True)
        self._started = False

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                return
            await self._load_state()
            for _ in range(self.worker_count):
                worker = asyncio.create_task(self._worker_loop(), name="tasker-worker")
                self._workers.append(worker)
            self._started = True
            logger.info("Tasker started with {} workers", self.worker_count)

    async def shutdown(self) -> None:
        async with self._lock:
            if not self._started:
                return
            for worker in self._workers:
                worker.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()
            await self._persist_state()
            self._started = False
            logger.info("Tasker shutdown complete")

    async def enqueue(
        self,
        *,
        name: str,
        task_type: str,
        payload: dict[str, Any] | None = None,
        coroutine: TaskCoroutine,
    ) -> Task:
        task_id = uuid.uuid4().hex
        task = Task(id=task_id, name=name, type=task_type, payload=payload or {})
        async with self._lock:
            self._tasks[task_id] = task
            await self._persist_state()
            await self._queue.put((task_id, coroutine))
        logger.info("Enqueued task {} ({})", task_id, name)
        return task

    async def list_tasks(self, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        async with self._lock:
            all_tasks = list(self._tasks.values())

        status_counter = Counter(task.status for task in all_tasks)
        type_counter = Counter(task.type for task in all_tasks)
        all_tasks.sort(key=lambda item: item.created_at or utc_isoformat(), reverse=True)

        tasks = all_tasks
        if status:
            tasks = [task for task in tasks if task.status == status]

        limited_tasks = tasks[: max(limit, 0)]

        summary: dict[str, Any] = {
            "total": len(all_tasks),
            "filtered_total": len(tasks),
            "status_counts": dict(status_counter),
            "type_counts": dict(type_counter),
        }

        return {
            "tasks": [task.to_summary_dict() for task in limited_tasks],
            "summary": summary,
        }

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        async with self._lock:
            task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status in {"success", "failed", "cancelled"}:
                return False
            task.cancel_requested = True
            task.updated_at = _utc_timestamp()
            await self._persist_state()
        logger.info("Cancellation requested for task {}", task_id)
        return True

    async def _worker_loop(self) -> None:
        while True:
            try:
                task_id, coroutine = await self._queue.get()
                try:
                    task = await self._get_task_instance(task_id)
                    if not task:
                        continue
                    if task.cancel_requested:
                        await self._mark_cancelled(task_id, "Task was cancelled before execution")
                        continue
                    await self._update_task(
                        task_id, status="running", progress=0.0, message="任务开始执行", started_at=_utc_timestamp()
                    )
                    context = TaskContext(self, task_id)
                    try:
                        result = await coroutine(context)
                        if task.cancel_requested:
                            await self._mark_cancelled(task_id, "Task cancelled during execution")
                            continue
                        await self._update_task(
                            task_id,
                            status="success",
                            progress=100.0,
                            message="任务已完成",
                            result=result,
                            completed_at=_utc_timestamp(),
                        )
                    except asyncio.CancelledError:
                        await self._mark_cancelled(task_id, "任务被取消")
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Task {} failed: {}", task_id, exc)
                        await self._update_task(
                            task_id,
                            status="failed",
                            progress=100.0,
                            message="任务执行失败",
                            error=str(exc),
                            completed_at=_utc_timestamp(),
                        )
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("Tasker worker error: {}", exc)

    async def _get_task_instance(self, task_id: str) -> Task | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def _mark_cancelled(self, task_id: str, message: str) -> None:
        await self._update_task(
            task_id,
            status="cancelled",
            progress=100.0,
            message=message,
            completed_at=_utc_timestamp(),
        )

    async def _update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        result: Any = None,
        error: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            if status:
                task.status = status
            if progress is not None:
                task.progress = max(0.0, min(progress, 100.0))
            if message is not None:
                task.message = message
            if result is not None:
                task.result = result
            if error is not None:
                task.error = error
            if started_at is not None:
                task.started_at = started_at
            if completed_at is not None:
                task.completed_at = completed_at
            task.updated_at = _utc_timestamp()
            await self._persist_state()

    def _is_cancel_requested(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        return bool(task and task.cancel_requested)

    async def _load_state(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            content = await asyncio.to_thread(self._storage_path.read_text, encoding="utf-8")
            if not content.strip():
                return
            data = json.loads(content)
            tasks = data.get("tasks", [])
            for item in tasks:
                task = Task.from_dict(item)
                if task.status == "running":
                    task.status = "failed"
                    task.message = "服务重启时任务中断"
                    task.updated_at = _utc_timestamp()
                elif task.status not in TERMINAL_STATUSES:
                    task.status = "failed"
                    task.message = "服务重启时任务未继续执行"
                    task.updated_at = _utc_timestamp()
                self._tasks[task.id] = task
            logger.info("Loaded {} task records from storage", len(tasks))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load task state: {}", exc)

    async def _persist_state(self) -> None:
        tasks = [task.to_dict() for task in self._tasks.values()]
        payload = {"tasks": tasks, "updated_at": _utc_timestamp()}

        def _write() -> None:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._storage_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._storage_path)

        await asyncio.to_thread(_write)


tasker = Tasker()


__all__ = ["tasker", "TaskContext", "Tasker"]
