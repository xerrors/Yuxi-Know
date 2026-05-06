import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

from yuxi.knowledge import knowledge_base
from yuxi.knowledge.eval.benchmark_generation import dump_benchmark_item, iter_generated_benchmark_items
from yuxi.knowledge.eval.evaluator import aggregate_metrics, evaluate_question
from yuxi.models import select_model
from yuxi.repositories.evaluation_repository import EvaluationRepository
from yuxi.repositories.knowledge_base_repository import KnowledgeBaseRepository
from yuxi.services.task_service import TaskContext, tasker
from yuxi.utils import logger


class EvaluationService:
    """RAG评估服务"""

    def __init__(self):
        self.eval_repo = EvaluationRepository()
        self.kb_repo = KnowledgeBaseRepository()

    async def _get_benchmark_dir(self, db_id: str) -> str:
        """获取评估基准目录"""
        kb_instance = await knowledge_base.aget_kb(db_id)
        base_dir = os.path.join(kb_instance.work_dir, db_id)
        path = os.path.join(base_dir, "benchmarks")
        os.makedirs(path, exist_ok=True)
        return path

    async def _get_result_dir(self, db_id: str) -> str:
        """获取评估结果目录"""
        kb_instance = await knowledge_base.aget_kb(db_id)
        base_dir = os.path.join(kb_instance.work_dir, db_id)
        path = os.path.join(base_dir, "results")
        os.makedirs(path, exist_ok=True)
        return path

    # 已移除基准回退逻辑，统一使用集中元数据

    # 已移除结果回退逻辑，统一通过 db_id 定位

    async def upload_benchmark(
        self, db_id: str, file_content: bytes, filename: str, name: str, description: str, created_by: str
    ) -> dict[str, Any]:
        """上传评估基准文件"""
        try:
            content_str = file_content.decode("utf-8")
            questions = []
            has_gold_chunks = False
            has_gold_answers = False

            # 解析 JSONL
            for line_num, line in enumerate(content_str.strip().split("\n"), 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    if "query" not in item:
                        raise ValueError(f"第{line_num}行缺少必需的'query'字段")
                    if item.get("gold_chunk_ids"):
                        has_gold_chunks = True
                    if item.get("gold_answer"):
                        has_gold_answers = True
                    questions.append(item)
                except json.JSONDecodeError as e:
                    raise ValueError(f"第{line_num}行JSON格式错误: {str(e)}")

            if not questions:
                raise ValueError("文件中没有有效的问题数据")

            benchmark_id = f"benchmark_{uuid.uuid4().hex[:8]}"
            benchmark_dir = await self._get_benchmark_dir(db_id)

            # 保存数据文件 (.jsonl)
            data_file_path = os.path.join(benchmark_dir, f"{benchmark_id}.jsonl")
            with open(data_file_path, "w", encoding="utf-8") as f:
                f.write(content_str)

            meta = {
                "id": benchmark_id,
                "benchmark_id": benchmark_id,
                "name": name,
                "description": description,
                "db_id": db_id,
                "question_count": len(questions),
                "has_gold_chunks": has_gold_chunks,
                "has_gold_answers": has_gold_answers,
                "benchmark_file": data_file_path,
                "created_by": created_by,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            await self.eval_repo.create_benchmark(
                {
                    "benchmark_id": benchmark_id,
                    "db_id": db_id,
                    "name": name,
                    "description": description,
                    "question_count": len(questions),
                    "has_gold_chunks": has_gold_chunks,
                    "has_gold_answers": has_gold_answers,
                    "data_file_path": data_file_path,
                    "created_by": created_by,
                }
            )
            return meta

        except Exception as e:
            logger.error(f"上传评估基准失败: {e}")
            raise

    async def get_benchmarks(self, db_id: str) -> list[dict[str, Any]]:
        """获取知识库的评估基准列表"""
        try:
            rows = await self.eval_repo.list_benchmarks(db_id)
            return [
                {
                    "id": row.benchmark_id,
                    "benchmark_id": row.benchmark_id,
                    "name": row.name,
                    "description": row.description,
                    "db_id": row.db_id,
                    "question_count": row.question_count,
                    "has_gold_chunks": row.has_gold_chunks,
                    "has_gold_answers": row.has_gold_answers,
                    "benchmark_file": row.data_file_path,
                    "created_by": row.created_by,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"获取评估基准列表失败: {e}")
            raise

    async def get_benchmark_detail(self, benchmark_id: str) -> dict[str, Any]:
        """获取评估基准详情 (包含问题列表)"""
        try:
            row = await self.eval_repo.get_benchmark(benchmark_id)
            if row is None:
                raise ValueError("Benchmark not found")
            questions = []
            if row.data_file_path and os.path.exists(row.data_file_path):
                with open(row.data_file_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            questions.append(json.loads(line))
            return {
                "id": row.benchmark_id,
                "benchmark_id": row.benchmark_id,
                "name": row.name,
                "description": row.description,
                "db_id": row.db_id,
                "question_count": row.question_count,
                "has_gold_chunks": row.has_gold_chunks,
                "has_gold_answers": row.has_gold_answers,
                "benchmark_file": row.data_file_path,
                "created_by": row.created_by,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "questions": questions,
            }

        except Exception as e:
            logger.error(f"获取评估基准详情失败: {e}")
            raise

    async def get_benchmark_detail_by_db(
        self, db_id: str, benchmark_id: str, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        """根据 db_id 获取评估基准详情（支持分页）"""
        try:
            row = await self.eval_repo.get_benchmark(benchmark_id)
            if row is None or row.db_id != db_id:
                raise ValueError("Benchmark not found")
            data_file_path = row.data_file_path
            total_questions = row.question_count or 0
            questions = []

            if data_file_path and os.path.exists(data_file_path):
                # 计算分页范围
                start_index = (page - 1) * page_size
                end_index = start_index + page_size

                # 读取指定范围的问题
                with open(data_file_path, encoding="utf-8") as f:
                    current_index = 0
                    for line in f:
                        if not line.strip():
                            continue

                        # 只处理指定范围内的问题
                        if current_index >= start_index and current_index < end_index:
                            questions.append(json.loads(line))
                        elif current_index >= end_index:
                            break  # 已经读取到足够的问题，停止读取

                        current_index += 1

            # 计算分页信息
            total_pages = (total_questions + page_size - 1) // page_size

            return {
                "id": row.benchmark_id,
                "benchmark_id": row.benchmark_id,
                "name": row.name,
                "description": row.description,
                "db_id": row.db_id,
                "question_count": row.question_count,
                "has_gold_chunks": row.has_gold_chunks,
                "has_gold_answers": row.has_gold_answers,
                "benchmark_file": data_file_path,
                "created_by": row.created_by,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "questions": questions,
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total_questions": total_questions,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
            }
        except Exception as e:
            logger.error(f"获取评估基准详情失败: {e}")
            raise

    async def get_benchmark_download_info(self, benchmark_id: str) -> dict[str, str]:
        """获取评估基准下载信息"""
        row = await self.eval_repo.get_benchmark(benchmark_id)
        if row is None:
            raise ValueError("Benchmark not found")

        data_file_path = row.data_file_path or ""
        if not data_file_path or not os.path.exists(data_file_path):
            raise ValueError("Benchmark file not found")

        filename_base = (row.name or "").strip()
        if not filename_base:
            filename_base = row.benchmark_id

        filename_base = re.sub(r"[\\/:*?\"<>|]+", "_", filename_base).strip()
        if not filename_base or filename_base in {".", ".."}:
            filename_base = row.benchmark_id

        if not filename_base.endswith(".jsonl"):
            filename_base = f"{filename_base}.jsonl"

        return {"file_path": data_file_path, "filename": filename_base}

    async def delete_benchmark(self, benchmark_id: str) -> None:
        """删除评估基准"""
        try:
            row = await self.eval_repo.get_benchmark(benchmark_id)
            if row is None:
                raise ValueError("Benchmark not found")
            if row.data_file_path and os.path.exists(row.data_file_path):
                os.remove(row.data_file_path)
            await self.eval_repo.delete_benchmark(benchmark_id)
            logger.info(f"成功删除评估基准: {benchmark_id}")
            return

        except Exception as e:
            logger.error(f"删除评估基准失败: {e}")
            raise

    async def delete_evaluation_result(self, task_id: str, db_id: str) -> None:
        """删除评估结果"""
        if not task_id:
            raise ValueError("task_id is required")
        await self.delete_evaluation_result_by_db(db_id, task_id)

    async def generate_benchmark(self, db_id: str, params: dict[str, Any], created_by: str) -> dict[str, Any]:
        task_id = f"gen_benchmark_{uuid.uuid4().hex[:8]}"
        await tasker.enqueue(
            name="生成评估基准",
            task_type="benchmark_generation",
            payload={"task_id": task_id, "db_id": db_id, "created_by": created_by, **params},
            coroutine=self._generate_benchmark_task,
        )
        return {"task_id": task_id, "message": "基准生成任务已提交"}

    async def _generate_benchmark_task(self, context: TaskContext):
        await context.set_progress(0, "初始化")

        task = context._tasker._tasks.get(context.task_id)
        payload = task.payload if task else {}

        db_id = payload.get("db_id")
        name = payload.get("name", "自动生成评估基准")
        description = payload.get("description", "")
        count = int(payload.get("count", 10))
        neighbors_count = int(payload.get("neighbors_count", 1))
        llm_model_spec = payload.get("llm_model_spec")

        kb_instance = await knowledge_base.aget_kb(db_id)
        if not kb_instance:
            await context.set_message("知识库不存在")
            raise ValueError("Knowledge Base not found")
        if kb_instance.kb_type != "milvus":
            await context.set_message("仅支持 commonrag/Milvus 类型知识库生成评估基准")
            raise ValueError("Unsupported KB type for benchmark generation")

        benchmark_id = f"benchmark_{uuid.uuid4().hex[:8]}"
        bench_dir = await self._get_benchmark_dir(db_id)
        data_file_path = os.path.join(bench_dir, f"{benchmark_id}.jsonl")
        generated = 0

        try:
            with open(data_file_path, "w", encoding="utf-8") as f:
                async for item in iter_generated_benchmark_items(
                    kb_instance=kb_instance,
                    db_id=db_id,
                    count=count,
                    neighbors_count=neighbors_count,
                    llm_model_spec=llm_model_spec,
                    progress_cb=context.set_progress,
                ):
                    f.write(dump_benchmark_item(item))
                    generated += 1
        except ValueError as e:
            if str(e) == "No chunks found in knowledge base":
                await context.set_message("知识库为空或未解析到chunks")
            raise

        await self.eval_repo.create_benchmark(
            {
                "benchmark_id": benchmark_id,
                "db_id": db_id,
                "name": name,
                "description": description,
                "question_count": generated,
                "has_gold_chunks": True,
                "has_gold_answers": True,
                "data_file_path": data_file_path,
                "created_by": payload.get("created_by"),
            }
        )

        await context.set_progress(100, "完成")

    async def run_evaluation(
        self, db_id: str, benchmark_id: str, model_config: dict[str, Any] = None, created_by: str = "system"
    ) -> str:
        """运行RAG评估"""
        try:
            task_id = f"eval_{uuid.uuid4().hex[:8]}"

            benchmark_row = await self.eval_repo.get_benchmark(benchmark_id)
            if benchmark_row is None or benchmark_row.db_id != db_id:
                raise ValueError("Benchmark not found")

            # 从知识库元数据中获取检索配置
            retrieval_config = {}
            try:
                kb_row = await self.kb_repo.get_by_id(db_id)
                query_params = (kb_row.query_params if kb_row else None) or {}
                retrieval_config = query_params.get("options", {}) if isinstance(query_params, dict) else {}
                logger.info(f"从知识库 {db_id} 加载检索配置: {list(retrieval_config.keys())}")
            except Exception as e:
                logger.error(f"获取知识库检索配置失败: {e}")
                # 使用空配置作为默认值

            # 合并前端传递的模型配置
            if model_config:
                retrieval_config.update(model_config)

            await self.eval_repo.create_result(
                {
                    "task_id": task_id,
                    "db_id": db_id,
                    "benchmark_id": benchmark_id,
                    "status": "running",
                    "retrieval_config": retrieval_config,
                    "metrics": {},
                    "overall_score": None,
                    "total_questions": benchmark_row.question_count or 0,
                    "completed_questions": 0,
                    "started_at": datetime.utcnow(),
                    "completed_at": None,
                    "created_by": created_by,
                }
            )

            await tasker.enqueue(
                name=f"RAG评估({benchmark_row.name})",
                task_type="rag_evaluation",
                payload={
                    "task_id": task_id,
                    "db_id": db_id,
                    "benchmark_id": benchmark_id,
                    "retrieval_config": retrieval_config,
                    "created_by": created_by,
                },
                coroutine=self._run_evaluation_task,
            )

            return task_id

        except Exception as e:
            logger.error(f"启动评估失败: {e}")
            raise

    async def _run_evaluation_task(self, context: TaskContext):
        """运行评估任务"""
        try:
            task = context._tasker._tasks.get(context.task_id)
            if not task:
                raise ValueError("Task not found")
            payload = task.payload

            task_id = payload["task_id"]
            db_id = payload["db_id"]
            benchmark_id = payload["benchmark_id"]
            retrieval_config = payload["retrieval_config"]

            # 加载基准数据
            await context.set_progress(5, "加载基准数据")
            benchmark_row = await self.eval_repo.get_benchmark(benchmark_id)
            if benchmark_row is None or benchmark_row.db_id != db_id:
                raise ValueError("Benchmark not found")
            data_path = benchmark_row.data_file_path
            if not data_path or not os.path.exists(data_path):
                raise ValueError("Benchmark file not found")

            benchmark_data = []
            with open(data_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        benchmark_data.append(json.loads(line))

            # 开始评估
            kb_instance = await knowledge_base.aget_kb(db_id)
            if not kb_instance:
                raise ValueError(f"Knowledge Base {db_id} not found")

            if kb_instance.kb_type == "lightrag":
                raise ValueError("暂不支持对 LightRAG 类型的知识库进行 RAG 评估")

            # 初始化 Judge LLM
            judge_llm = None
            if benchmark_row.has_gold_answers:
                # 优先使用配置中的 judge_llm，否则回退到 answer_llm，或者默认
                judge_model_spec = retrieval_config.get("judge_llm") or retrieval_config.get("answer_llm")
                if judge_model_spec:
                    try:
                        logger.debug(f"Initializing Judge LLM: {judge_model_spec}")
                        judge_llm = select_model(model_spec=judge_model_spec)
                    except Exception as e:
                        logger.error(f"Failed to load judge LLM: {e}")

            total_questions = len(benchmark_data)
            all_retrieval_metrics = []
            all_answer_metrics = []

            async def update_result_db(
                status: str | None = None, completed: int | None = None, metrics=None, final_score=None
            ):
                payload = {}
                if status is not None:
                    payload["status"] = status
                    if status in ["completed", "failed"]:
                        payload["completed_at"] = datetime.utcnow()
                if completed is not None:
                    payload["completed_questions"] = completed
                if metrics is not None:
                    payload["metrics"] = metrics
                if final_score is not None:
                    payload["overall_score"] = final_score
                if payload:
                    await self.eval_repo.update_result(task_id, payload)

            for i, question_data in enumerate(benchmark_data):
                await context.raise_if_cancelled()
                progress = 10 + (i / total_questions) * 80
                await context.set_progress(progress, f"评估 {i + 1}/{total_questions}")

                question_result = await evaluate_question(
                    kb_instance=kb_instance,
                    db_id=db_id,
                    question_data=question_data,
                    retrieval_config=retrieval_config,
                    has_gold_chunks=benchmark_row.has_gold_chunks,
                    has_gold_answers=benchmark_row.has_gold_answers,
                    judge_llm=judge_llm,
                    select_model_fn=select_model,
                )

                if benchmark_row.has_gold_chunks and question_data.get("gold_chunk_ids"):
                    all_retrieval_metrics.append(question_result["retrieval_scores"])
                if benchmark_row.has_gold_answers and question_data.get("gold_answer") and judge_llm:
                    all_answer_metrics.append(question_result["answer_scores"])

                await self.eval_repo.upsert_result_detail(
                    task_id=task_id,
                    query_index=i,
                    data=question_result["detail"],
                )

                current_overall_metrics, _ = aggregate_metrics(all_retrieval_metrics, all_answer_metrics)
                await context.set_result(
                    {
                        "current_metrics": current_overall_metrics,
                        "completed_questions": i + 1,
                        "total_questions": total_questions,
                    }
                )

                if (i + 1) % 5 == 0 or (i + 1) == total_questions:
                    await update_result_db(completed=i + 1)

            await context.set_progress(95, "计算最终指标")
            overall_metrics, overall_score = aggregate_metrics(
                all_retrieval_metrics, all_answer_metrics, include_overall_score=True
            )

            await update_result_db(
                status="completed",
                completed=total_questions,
                metrics=overall_metrics,
                final_score=overall_score,
            )
            await context.set_progress(100, "完成")

        except Exception as e:
            logger.error(f"Task failed: {e}")
            try:
                if "payload" in locals():
                    await self.eval_repo.update_result(
                        payload["task_id"],
                        {"status": "failed", "metrics": {"error": str(e)}, "completed_at": datetime.utcnow()},
                    )
            except Exception as exc:
                logger.error(f"Error updating result record: {exc}")

            await context.set_message(f"Error: {str(e)}")
            raise

    async def get_evaluation_results(self, task_id: str, db_id: str) -> dict[str, Any]:
        """获取评估结果"""
        if not task_id:
            raise ValueError("task_id is required")
        return await self.get_evaluation_results_by_db(db_id, task_id)

    async def get_evaluation_history(self, db_id: str) -> list[dict[str, Any]]:
        """获取知识库的评估历史记录"""
        try:
            rows = await self.eval_repo.list_results(db_id)
            return [
                {
                    "task_id": row.task_id,
                    "benchmark_id": row.benchmark_id,
                    "status": row.status,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                    "total_questions": row.total_questions,
                    "completed_questions": row.completed_questions,
                    "overall_score": row.overall_score,
                    "retrieval_config": row.retrieval_config or {},
                    "metrics": row.metrics or {},
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"获取评估历史失败: {e}")
            raise
        # 索引与回退逻辑已移除，统一通过 db_id 定位

    async def get_evaluation_results_by_db(
        self, db_id: str, task_id: str, page: int = 1, page_size: int = 20, error_only: bool = False
    ) -> dict[str, Any]:
        if not re.match(r"^eval_[a-f0-9]{8}$", task_id):
            raise ValueError("Invalid task_id format")
        row = await self.eval_repo.get_result(task_id)
        if row is None or row.db_id != db_id:
            task = await tasker.get_task(task_id)
            if task:
                return {"task_id": task_id, "status": task.status, "progress": task.progress, "message": task.message}
            raise ValueError(f"Result not found for task {task_id}")

        details = await self.eval_repo.list_result_details(task_id)
        all_results = [
            {
                "query": d.query_text,
                "gold_chunk_ids": d.gold_chunk_ids,
                "gold_answer": d.gold_answer,
                "generated_answer": d.generated_answer,
                "retrieved_chunks": d.retrieved_chunks,
                "metrics": d.metrics or {},
            }
            for d in details
        ]

        if error_only:
            filtered_results = []
            for item in all_results:
                if item.get("metrics", {}).get("score", 1.0) <= 0.5:
                    filtered_results.append(item)
                    continue
                metrics = item.get("metrics", {})
                has_low_recall = any(metrics.get(k, 1.0) < 0.3 for k in metrics if k.startswith("recall@"))
                if has_low_recall:
                    filtered_results.append(item)
            all_results = filtered_results

        total = len(all_results)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_results = all_results[start_idx:end_idx]

        return {
            "task_id": row.task_id,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "total_questions": row.total_questions or 0,
            "completed_questions": row.completed_questions or 0,
            "overall_score": row.overall_score,
            "retrieval_config": row.retrieval_config or {},
            "interim_results": paged_results,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
                "error_only": error_only,
            },
        }

    async def delete_evaluation_result_by_db(self, db_id: str, task_id: str) -> None:
        if not re.match(r"^eval_[a-f0-9]{8}$", task_id):
            raise ValueError("Invalid task_id format")
        row = await self.eval_repo.get_result(task_id)
        if row is None or row.db_id != db_id:
            raise ValueError("Result not found")
        await self.eval_repo.delete_result(task_id)
        logger.info(f"成功删除评估结果: {task_id}")
        return
