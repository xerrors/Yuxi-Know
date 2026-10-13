from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, or_, select
from yuxi.shared.datetime import utc_now

from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.knowledge.models import EvaluationDataset, EvaluationDatasetItem, EvaluationRun, EvaluationRunItem


class EvaluationRepository:
    @staticmethod
    async def create_dataset_in_session(session, dataset_data: dict[str, Any]) -> EvaluationDataset:
        """在 service 拥有的事务中创建数据集。"""
        dataset = EvaluationDataset(**dataset_data)
        session.add(dataset)
        await session.flush()
        return dataset

    async def create_dataset_with_items(self, dataset_data: dict[str, Any], items_data: list[dict[str, Any]]) -> EvaluationDataset:
        async with pg_manager.get_async_session_context() as session:
            dataset = await self.create_dataset_in_session(session, dataset_data)
            await self.add_dataset_items_in_session(session, items_data)
            return dataset

    @staticmethod
    async def attach_dataset_generation_job_in_session(
        session,
        dataset_id: str,
        job_id: str,
    ) -> EvaluationDataset | None:
        """在调用方事务中关联生成作业，且不覆盖相同作业的终态。"""
        record = await session.scalar(select(EvaluationDataset).where(EvaluationDataset.dataset_id == dataset_id).with_for_update())
        if record is None:
            return None
        metadata = dict(record.build_metadata or {})
        if metadata.get("source") != "generated" or metadata.get("status") == "completed":
            return record
        if metadata.get("job_id") == job_id:
            return record
        metadata.update(
            job_id=job_id,
            status="pending",
            message="等待 worker 执行",
        )
        metadata.pop("error_message", None)
        record.build_metadata = metadata
        await session.flush()
        return record

    @staticmethod
    async def update_dataset_in_session(session, dataset_id: str, data: dict[str, Any]) -> EvaluationDataset | None:
        record = await session.scalar(select(EvaluationDataset).where(EvaluationDataset.dataset_id == dataset_id).with_for_update())
        if record is None:
            return None
        for key, value in data.items():
            setattr(record, key, value)
        await session.flush()
        return record

    async def update_dataset(self, dataset_id: str, data: dict[str, Any]) -> EvaluationDataset | None:
        async with pg_manager.get_async_session_context() as session:
            return await self.update_dataset_in_session(session, dataset_id, data)

    @staticmethod
    async def add_dataset_items_in_session(session, items_data: list[dict[str, Any]]) -> None:
        session.add_all(EvaluationDatasetItem(**item) for item in items_data)
        await session.flush()

    async def get_dataset(self, dataset_id: str) -> EvaluationDataset | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EvaluationDataset).where(EvaluationDataset.dataset_id == dataset_id))
            return result.scalar_one_or_none()

    async def list_datasets(self, kb_id: str) -> list[EvaluationDataset]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationDataset).where(EvaluationDataset.kb_id == kb_id).order_by(EvaluationDataset.created_at.desc())
            )
            return list(result.scalars().all())

    async def list_dataset_items(self, dataset_id: str, offset: int = 0, limit: int = 100) -> list[EvaluationDatasetItem]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationDatasetItem)
                .where(EvaluationDatasetItem.dataset_id == dataset_id)
                .order_by(EvaluationDatasetItem.item_index.asc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def count_dataset_items(self, dataset_id: str) -> int:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(func.count(EvaluationDatasetItem.id)).where(EvaluationDatasetItem.dataset_id == dataset_id)
            )
            return int(result.scalar() or 0)

    async def list_all_dataset_items(self, dataset_id: str) -> list[EvaluationDatasetItem]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationDatasetItem)
                .where(EvaluationDatasetItem.dataset_id == dataset_id)
                .order_by(EvaluationDatasetItem.item_index.asc())
            )
            return list(result.scalars().all())

    async def delete_dataset(self, dataset_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EvaluationDataset).where(EvaluationDataset.dataset_id == dataset_id))
            record = result.scalar_one_or_none()
            if record is not None:
                await session.delete(record)

    @staticmethod
    async def create_run_in_session(session, data: dict[str, Any]) -> EvaluationRun:
        """在 service 拥有的事务中创建评估 Run。"""
        run = EvaluationRun(**data)
        session.add(run)
        await session.flush()
        return run

    async def get_run(self, run_id: str) -> EvaluationRun | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EvaluationRun).where(EvaluationRun.run_id == run_id))
            return result.scalar_one_or_none()

    async def list_runs(self, kb_id: str) -> list[EvaluationRun]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationRun).where(EvaluationRun.kb_id == kb_id).order_by(EvaluationRun.started_at.desc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def update_run_in_session(session, run_id: str, data: dict[str, Any]) -> EvaluationRun | None:
        record = await session.scalar(select(EvaluationRun).where(EvaluationRun.run_id == run_id).with_for_update())
        if record is None:
            return None
        for key, value in data.items():
            setattr(record, key, value)
        await session.flush()
        return record

    async def update_run(self, run_id: str, data: dict[str, Any]) -> EvaluationRun | None:
        async with pg_manager.get_async_session_context() as session:
            return await self.update_run_in_session(session, run_id, data)

    async def delete_run(self, run_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EvaluationRunItem).where(EvaluationRunItem.run_id == run_id))
            result = await session.execute(select(EvaluationRun).where(EvaluationRun.run_id == run_id))
            record = result.scalar_one_or_none()
            if record is not None:
                await session.delete(record)

    @staticmethod
    async def upsert_run_item_in_session(
        session,
        run_id: str,
        item_index: int,
        data: dict[str, Any],
    ) -> EvaluationRunItem:
        """绑定父运行的数据集；不能把其他数据集的题目写入当前结果。"""
        data = dict(data)
        if data.get("dataset_item_id") is not None:
            run = await session.scalar(select(EvaluationRun).where(EvaluationRun.run_id == run_id).with_for_update())
            if run is None or run.dataset_id is None:
                raise ValueError("评估运行没有可关联的数据集")
            data["dataset_id"] = run.dataset_id
        elif "dataset_item_id" in data:
            data["dataset_id"] = None
        record = await session.scalar(
            select(EvaluationRunItem)
            .where(EvaluationRunItem.run_id == run_id, EvaluationRunItem.item_index == item_index)
            .with_for_update()
        )
        if record is None:
            record = EvaluationRunItem(run_id=run_id, item_index=item_index, **data)
            session.add(record)
        else:
            for key, value in data.items():
                setattr(record, key, value)
        await session.flush()
        return record

    async def list_run_items(
        self, run_id: str, offset: int = 0, limit: int = 100, *, result_filter: str = "all"
    ) -> list[EvaluationRunItem]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationRunItem)
                .where(EvaluationRunItem.run_id == run_id, *self._result_filters(result_filter))
                .order_by(EvaluationRunItem.item_index.asc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def count_run_items(self, run_id: str, *, result_filter: str = "all") -> int:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(func.count(EvaluationRunItem.id)).where(EvaluationRunItem.run_id == run_id, *self._result_filters(result_filter))
            )
            return int(result.scalar() or 0)

    async def delete_all(self) -> None:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EvaluationRunItem))
            await session.execute(delete(EvaluationRun))
            await session.execute(delete(EvaluationDatasetItem))
            await session.execute(delete(EvaluationDataset))

    @staticmethod
    def _result_filters(result_filter: str) -> list:
        """在 SQL 中筛选后分页，缺失指标保留历史默认分值。"""
        if result_filter == "all":
            return []
        answer_error = func.coalesce(EvaluationRunItem.metrics["score"].as_float(), 1.0) <= 0.5
        if result_filter == "answer_errors":
            return [answer_error]
        return [or_(answer_error, func.coalesce(EvaluationRunItem.metrics["recall@10"].as_float(), 1.0) < 1)]


async def finish_dataset_generation_job(session, job_record, result) -> None:
    """在 BackgroundJob 成功事务内提交数据集完成事实。"""
    if not isinstance(result, dict) or result.get("dataset_id") != (job_record.payload or {}).get("dataset_id"):
        raise ValueError("Dataset generation result does not match BackgroundJob payload")
    dataset = await session.scalar(select(EvaluationDataset).where(EvaluationDataset.dataset_id == result["dataset_id"]).with_for_update())
    if dataset is None:
        raise ValueError("Dataset not found during BackgroundJob completion")
    dataset.item_count = int(result["item_count"])
    dataset.build_metadata = dict(result["build_metadata"])


async def fail_dataset_generation_job(session, job_record, error: str) -> None:
    """在 BackgroundJob 失败事务内收敛数据集构建状态。"""
    dataset_id = (job_record.payload or {}).get("dataset_id")
    dataset = await session.scalar(select(EvaluationDataset).where(EvaluationDataset.dataset_id == dataset_id).with_for_update())
    if dataset is None:
        return
    metadata = dict(dataset.build_metadata or {})
    if metadata.get("status") == "completed":
        return
    metadata.update(
        status="failed",
        job_id=job_record.id,
        progress=100,
        error_message=error,
        message=error,
    )
    dataset.build_metadata = metadata


async def finish_rag_evaluation_job(session, job_record, result) -> None:
    """在 BackgroundJob 成功事务内提交评估 Run 完成事实。"""
    if not isinstance(result, dict) or result.get("run_id") != (job_record.payload or {}).get("run_id"):
        raise ValueError("Evaluation result does not match BackgroundJob payload")
    run = await session.scalar(select(EvaluationRun).where(EvaluationRun.run_id == result["run_id"]).with_for_update())
    if run is None:
        raise ValueError("EvaluationRun not found during BackgroundJob completion")
    run.status = "completed"
    run.completed_items = int(result["completed_items"])
    run.metrics = dict(result["metrics"])
    run.overall_score = result["overall_score"]
    run.completed_at = utc_now()


async def fail_rag_evaluation_job(session, job_record, error: str) -> None:
    """在 BackgroundJob 失败事务内收敛评估 Run。"""
    run_id = (job_record.payload or {}).get("run_id")
    run = await session.scalar(select(EvaluationRun).where(EvaluationRun.run_id == run_id).with_for_update())
    if run is None or run.status == "completed":
        return
    run.status = "failed"
    run.metrics = {"error": error}
    run.completed_at = utc_now()
