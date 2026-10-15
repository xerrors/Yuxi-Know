from __future__ import annotations

import hashlib
import json
import math
import uuid
from typing import Any

from yuxi.modules.background_jobs.repository import BackgroundJobRepository
from yuxi.shared.datetime import utc_now
from yuxi.modules.background_jobs.models import BackgroundJobRecord


class JobTracker:
    """登记后台动作，保存执行方上报并提供查询和取消请求。"""

    def __init__(self):
        self._repo = BackgroundJobRepository()

    async def register(
        self,
        *,
        name: str,
        job_type: str,
        payload: dict[str, Any] | None = None,
        payload_match: dict[str, Any] | None = None,
        handler_version: int = 1,
        timeout_seconds: float = 21600.0,
    ) -> tuple[BackgroundJobRecord, bool]:
        """登记持久记录；执行方自行决定何时投递。"""
        record, created = await self._repo.create(
            uuid.uuid4().hex,
            self._registration_data(
                name=name,
                job_type=job_type,
                payload=payload or {},
                payload_match=payload_match,
                handler_version=handler_version,
                timeout_seconds=timeout_seconds,
            ),
        )
        return record, created

    async def register_in_session(
        self,
        session,
        *,
        name: str,
        job_type: str,
        payload: dict[str, Any],
        payload_match: dict[str, Any] | None = None,
        handler_version: int = 1,
        timeout_seconds: float = 21600.0,
    ) -> tuple[BackgroundJobRecord, bool]:
        """在业务方拥有的事务中登记，事务提交由业务方负责。"""
        record, created = await self._repo.create_or_get_in_session(
            session,
            uuid.uuid4().hex,
            self._registration_data(
                name=name,
                job_type=job_type,
                payload=payload,
                payload_match=payload_match,
                handler_version=handler_version,
                timeout_seconds=timeout_seconds,
            ),
        )
        return record, created

    async def report(
        self,
        job_id: str,
        *,
        worker_id: str,
        progress: float | None = None,
        message: str | None = None,
        result: Any = ...,
    ) -> bool:
        """保存有效执行方的进度与结果；上报不改变任务成败。"""
        data: dict[str, Any] = {}
        if progress is not None:
            progress = float(progress)
            if not math.isfinite(progress):
                raise ValueError("BackgroundJob progress must be finite")
            data["progress"] = max(0.0, min(progress, 100.0))
        if message is not None:
            data["message"] = message
        if result is not ...:
            data["result"] = result
        return await self._repo.update_owned(job_id, worker_id=worker_id, data=data)

    async def find_job_by_payload(
        self, *, job_type: str, payload_match: dict[str, Any], statuses: set[str] | None = None
    ) -> BackgroundJobRecord | None:
        record = await self._repo.find_latest_by_payload(
            job_type=job_type,
            payload_match=payload_match,
            statuses=statuses,
        )
        return record

    async def list_jobs(self, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        records = await self._repo.list(status=status, limit=limit)
        return {
            "jobs": [record.to_summary_dict() for record in records],
            "summary": await self._repo.summarize(status=status),
        }

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        record = await self._repo.get_by_id(job_id)
        return record.to_observation_dict() if record else None

    async def cancel_job(self, job_id: str) -> BackgroundJobRecord | None:
        """只登记取消意图，执行方确认停止后再上报终态。"""
        record = await self._repo.request_cancel(job_id)
        return record

    async def delete_job(self, job_id: str) -> bool:
        return await self._repo.delete_terminal(job_id)

    @staticmethod
    def _registration_data(
        *,
        name: str,
        job_type: str,
        payload: dict[str, Any],
        payload_match: dict[str, Any] | None,
        handler_version: int,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        now = utc_now()
        dedupe_key = None
        if payload_match is not None:
            serialized = json.dumps(payload_match, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            dedupe_key = hashlib.sha256(f"{job_type}:{serialized}".encode()).hexdigest()
        return {
            "name": name,
            "type": job_type,
            "status": "pending",
            "progress": 0.0,
            "message": "任务已登记",
            "payload": payload,
            "handler_version": handler_version,
            "dedupe_key": dedupe_key,
            "timeout_seconds": timeout_seconds,
            "created_at": now,
            "updated_at": now,
        }


job_tracker = JobTracker()
