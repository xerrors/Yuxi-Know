from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from src.storage.postgres.models_knowledge import EvaluationBenchmark, EvaluationResult, EvaluationResultDetail
from src.storage.postgres.manager import pg_manager


class EvaluationRepository:
    async def get_all_benchmarks(self) -> list[EvaluationBenchmark]:
        """获取所有评估基准"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EvaluationBenchmark))
            return list(result.scalars().all())

    async def create_benchmark(self, data: dict[str, Any]) -> EvaluationBenchmark:
        benchmark = EvaluationBenchmark(**data)
        async with pg_manager.get_async_session_context() as session:
            session.add(benchmark)
        return benchmark

    async def get_benchmark(self, benchmark_id: str) -> EvaluationBenchmark | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationBenchmark).where(EvaluationBenchmark.benchmark_id == benchmark_id)
            )
            return result.scalar_one_or_none()

    async def list_benchmarks(self, db_id: str) -> list[EvaluationBenchmark]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationBenchmark)
                .where(EvaluationBenchmark.db_id == db_id)
                .order_by(EvaluationBenchmark.created_at.desc())
            )
            return list(result.scalars().all())

    async def delete_benchmark(self, benchmark_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationBenchmark).where(EvaluationBenchmark.benchmark_id == benchmark_id)
            )
            record = result.scalar_one_or_none()
            if record is not None:
                await session.delete(record)

    async def create_result(self, data: dict[str, Any]) -> EvaluationResult:
        result_row = EvaluationResult(**data)
        async with pg_manager.get_async_session_context() as session:
            session.add(result_row)
        return result_row

    async def get_result(self, task_id: str) -> EvaluationResult | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EvaluationResult).where(EvaluationResult.task_id == task_id))
            return result.scalar_one_or_none()

    async def list_results(self, db_id: str) -> list[EvaluationResult]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationResult)
                .where(EvaluationResult.db_id == db_id)
                .order_by(EvaluationResult.started_at.desc())
            )
            return list(result.scalars().all())

    async def update_result(self, task_id: str, data: dict[str, Any]) -> EvaluationResult | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(EvaluationResult).where(EvaluationResult.task_id == task_id))
            record = result.scalar_one_or_none()
            if record is None:
                return None
            for key, value in data.items():
                setattr(record, key, value)
            return record

    async def delete_result(self, task_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EvaluationResultDetail).where(EvaluationResultDetail.task_id == task_id))
            result = await session.execute(select(EvaluationResult).where(EvaluationResult.task_id == task_id))
            record = result.scalar_one_or_none()
            if record is not None:
                await session.delete(record)

    async def upsert_result_detail(
        self, task_id: str, query_index: int, data: dict[str, Any]
    ) -> EvaluationResultDetail:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationResultDetail).where(
                    (EvaluationResultDetail.task_id == task_id) & (EvaluationResultDetail.query_index == query_index)
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = EvaluationResultDetail(task_id=task_id, query_index=query_index, **data)
                session.add(record)
                return record
            for key, value in data.items():
                setattr(record, key, value)
            return record

    async def list_result_details(self, task_id: str) -> list[EvaluationResultDetail]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(EvaluationResultDetail)
                .where(EvaluationResultDetail.task_id == task_id)
                .order_by(EvaluationResultDetail.query_index.asc())
            )
            return list(result.scalars().all())

    async def delete_all(self) -> None:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(EvaluationResultDetail))
            await session.execute(delete(EvaluationResult))
            await session.execute(delete(EvaluationBenchmark))
