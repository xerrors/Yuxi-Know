import asyncio
import glob
import json
import os
import uuid
from datetime import datetime
from typing import Any

from server.services.tasker import TaskContext, tasker
from src.knowledge import knowledge_base
from src.models import select_model
from src.utils import logger
from src.utils.evaluation_metrics import EvaluationMetricsCalculator


class EvaluationService:
    """RAG评估服务 - 基于文件存储的版本"""

    def __init__(self):
        # 使用环境变量 DATA_DIR 或默认 'saves'
        self.data_dir = os.environ.get("DATA_DIR", "saves")
        self.root_eval_dir = os.path.join(self.data_dir, "evaluation")

    def _get_benchmark_dir(self, db_id: str) -> str:
        path = os.path.join(self.root_eval_dir, db_id, "benchmarks")
        os.makedirs(path, exist_ok=True)
        return path

    def _get_result_dir(self, db_id: str) -> str:
        path = os.path.join(self.root_eval_dir, db_id, "results")
        os.makedirs(path, exist_ok=True)
        return path

    def _find_benchmark_location(self, benchmark_id: str) -> tuple:
        """
        高效查找基准文件位置，返回 (db_id, meta_file_path)
        避免全局搜索，先检查是否有索引映射
        """
        # 由于当前文件结构限制，仍然需要搜索
        # 但可以优化搜索顺序和错误处理
        try:
            # 搜索所有 DB 目录找到该 benchmark
            pattern = os.path.join(self.root_eval_dir, "*", "benchmarks", f"{benchmark_id}.meta.json")
            matches = glob.glob(pattern)

            if not matches:
                raise ValueError(f"评估基准 {benchmark_id} 不存在")

            meta_file_path = matches[0]
            # 从路径推断 db_id (parent of parent)
            # path: .../{db_id}/benchmarks/{bid}.meta.json
            db_id = os.path.basename(os.path.dirname(os.path.dirname(meta_file_path)))

            return db_id, meta_file_path
        except Exception as e:
            logger.error(f"查找基准文件失败: {e}")
            raise

    def _find_result_location(self, task_id: str) -> tuple:
        """
        高效查找评估结果文件位置，返回 (db_id, result_file_path)
        """
        try:
            pattern = os.path.join(self.root_eval_dir, "*", "results", f"{task_id}.json")
            matches = glob.glob(pattern)

            if not matches:
                raise ValueError(f"评估结果 {task_id} 不存在")

            result_file_path = matches[0]
            # 从路径推断 db_id
            db_id = os.path.basename(os.path.dirname(os.path.dirname(result_file_path)))

            return db_id, result_file_path
        except Exception as e:
            logger.error(f"查找评估结果文件失败: {e}")
            raise

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
            benchmark_dir = self._get_benchmark_dir(db_id)

            # 保存数据文件 (.jsonl)
            data_file_path = os.path.join(benchmark_dir, f"{benchmark_id}.jsonl")
            with open(data_file_path, "w", encoding="utf-8") as f:
                f.write(content_str)

            # 保存元数据文件 (.meta.json)
            meta = {
                "id": benchmark_id,  # 前端期望字段可能是 id
                "benchmark_id": benchmark_id,
                "name": name,
                "description": description,
                "db_id": db_id,
                "question_count": len(questions),
                "has_gold_chunks": has_gold_chunks,
                "has_gold_answers": has_gold_answers,
                "created_by": created_by,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            meta_file_path = os.path.join(benchmark_dir, f"{benchmark_id}.meta.json")
            with open(meta_file_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            return meta

        except Exception as e:
            logger.error(f"上传评估基准失败: {e}")
            raise

    async def get_benchmarks(self, db_id: str) -> list[dict[str, Any]]:
        """获取知识库的评估基准列表"""
        try:
            benchmark_dir = self._get_benchmark_dir(db_id)
            benchmarks = []

            # 查找所有 .meta.json 文件
            meta_files = glob.glob(os.path.join(benchmark_dir, "*.meta.json"))
            for meta_file in meta_files:
                try:
                    with open(meta_file, encoding="utf-8") as f:
                        meta = json.load(f)
                        benchmarks.append(meta)
                except Exception as e:
                    logger.error(f"Failed to load benchmark meta {meta_file}: {e}")

            # 按创建时间倒序
            benchmarks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return benchmarks

        except Exception as e:
            logger.error(f"获取评估基准列表失败: {e}")
            raise

    async def get_benchmark_detail(self, benchmark_id: str) -> dict[str, Any]:
        """获取评估基准详情 (包含问题列表)"""
        try:
            # 使用优化的查找方法
            db_id, meta_file_path = self._find_benchmark_location(benchmark_id)

            with open(meta_file_path, encoding="utf-8") as f:
                found_meta = json.load(f)

            # 加载数据文件
            data_file_path = os.path.join(os.path.dirname(meta_file_path), f"{benchmark_id}.jsonl")
            questions = []
            if os.path.exists(data_file_path):
                with open(data_file_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            questions.append(json.loads(line))

            found_meta["questions"] = questions
            return found_meta

        except Exception as e:
            logger.error(f"获取评估基准详情失败: {e}")
            raise

    async def delete_benchmark(self, benchmark_id: str) -> None:
        """删除评估基准"""
        try:
            # 使用优化的查找方法
            _, meta_file_path = self._find_benchmark_location(benchmark_id)
            data_file_path = meta_file_path.replace(".meta.json", ".jsonl")

            if os.path.exists(meta_file_path):
                os.remove(meta_file_path)
            if os.path.exists(data_file_path):
                os.remove(data_file_path)

            logger.info(f"成功删除评估基准: {benchmark_id}")

        except Exception as e:
            logger.error(f"删除评估基准失败: {e}")
            raise

    async def delete_evaluation_result(self, task_id: str) -> None:
        """删除评估结果"""
        try:
            # 使用优化的查找方法
            _, result_file_path = self._find_result_location(task_id)

            # 删除结果文件
            os.remove(result_file_path)

            logger.info(f"成功删除评估结果: {task_id}")

        except Exception as e:
            logger.error(f"删除评估结果失败: {e}")
            raise

    async def generate_benchmark(self, db_id: str, params: dict[str, Any], created_by: str) -> dict[str, Any]:
        """自动生成评估基准 (Stub - Temporarily Disabled)"""
        # 保持与之前的逻辑一致：暂不支持自动生成
        # 我们可以保留接口但只返回错误，或者像之前一样进入 task 然后报错

        task_id = f"gen_benchmark_{uuid.uuid4().hex[:8]}"

        await tasker.enqueue(
            name="生成评估基准(Disabled)",
            task_type="benchmark_generation",
            payload={"task_id": task_id, "db_id": db_id, "created_by": created_by, **params},
            coroutine=self._generate_benchmark_task,
        )

        return {"task_id": task_id, "message": "基准生成任务已提交"}

    async def _generate_benchmark_task(self, context: TaskContext):
        """生成任务实现"""
        await context.set_progress(0, "初始化")
        raise NotImplementedError("自动生成基准功能暂时不可用，请手动上传基准文件。")

    async def run_evaluation(
        self, db_id: str, benchmark_id: str, model_config: dict[str, Any] = None, created_by: str = "system"
    ) -> str:
        """运行RAG评估"""
        try:
            task_id = f"eval_{uuid.uuid4().hex[:8]}"

            # 获取基准元数据以验证是否存在
            # 使用优化的查找方法
            _, meta_file_path = self._find_benchmark_location(benchmark_id)
            with open(meta_file_path, encoding="utf-8") as f:
                benchmark_meta = json.load(f)

            # 从知识库元数据中获取检索配置
            retrieval_config = {}
            try:
                kb_meta = knowledge_base.global_databases_meta.get(db_id, {})
                query_params = kb_meta.get("query_params", {})
                retrieval_config = query_params.get("options", {})
                logger.info(f"从知识库 {db_id} 加载检索配置: {list(retrieval_config.keys())}")
            except Exception as e:
                logger.error(f"获取知识库检索配置失败: {e}")
                # 使用空配置作为默认值

            # 合并前端传递的模型配置
            if model_config:
                retrieval_config.update(model_config)

            # 初始化结果文件 (Status: running)
            result_dir = self._get_result_dir(db_id)
            result_file_path = os.path.join(result_dir, f"{task_id}.json")

            initial_result = {
                "id": task_id,  # for compatibility
                "task_id": task_id,
                "benchmark_id": benchmark_id,
                "db_id": db_id,
                "retrieval_config": retrieval_config,
                "metrics": {},
                "status": "running",
                "total_questions": benchmark_meta.get("question_count", 0),
                "completed_questions": 0,
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": None,
                "interim_results": [],
            }

            with open(result_file_path, "w", encoding="utf-8") as f:
                json.dump(initial_result, f, ensure_ascii=False, indent=2)

            await tasker.enqueue(
                name=f"RAG评估({benchmark_meta.get('name')})",
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
            # 这里我们需要重新找到 benchmark file，因为 payload 里可能没有完整路径
            try:
                _, meta_path = self._find_benchmark_location(benchmark_id)
                data_path = meta_path.replace(".meta.json", ".jsonl")
            except ValueError:
                raise ValueError("Benchmark file not found")

            with open(meta_path, encoding="utf-8") as f:
                benchmark_meta = json.load(f)

            benchmark_data = []
            with open(data_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        benchmark_data.append(json.loads(line))

            # 开始评估
            kb_instance = knowledge_base.get_kb(db_id)
            if not kb_instance:
                raise ValueError(f"Knowledge Base {db_id} not found")

            if kb_instance.kb_type == "lightrag":
                raise ValueError("暂不支持对 LightRAG 类型的知识库进行 RAG 评估")

            # 初始化 Judge LLM
            judge_llm = None
            if benchmark_meta.get("has_gold_answers"):
                # 优先使用配置中的 judge_llm，否则回退到 answer_llm，或者默认
                judge_model_spec = retrieval_config.get("judge_llm") or retrieval_config.get("answer_llm")
                if judge_model_spec:
                    try:
                        logger.debug(f"Initializing Judge LLM: {judge_model_spec}")
                        judge_llm = select_model(model_spec=judge_model_spec)
                    except Exception as e:
                        logger.error(f"Failed to load judge LLM: {e}")

            total_questions = len(benchmark_data)
            interim_results = []
            all_retrieval_metrics = []
            all_answer_metrics = []

            # 更新结果文件 helper
            result_file_path = os.path.join(self._get_result_dir(db_id), f"{task_id}.json")

            def update_result_file(status="running", completed=0, metrics=None, interim=None, final_score=None):
                try:
                    if os.path.exists(result_file_path):
                        with open(result_file_path, encoding="utf-8") as f:
                            data = json.load(f)
                    else:
                        data = {}  # Should have been created in run_evaluation

                    data["status"] = status
                    data["completed_questions"] = completed
                    if metrics:
                        data["metrics"] = metrics
                    if interim is not None:
                        data["interim_results"] = interim
                    if final_score is not None:
                        data["overall_score"] = final_score
                    if status in ["completed", "failed"]:
                        data["completed_at"] = datetime.utcnow().isoformat()

                    with open(result_file_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"Failed to update result file: {e}")

            for i, question_data in enumerate(benchmark_data):
                # 检查任务是否被取消
                await context.raise_if_cancelled()
                progress = 10 + (i / total_questions) * 80
                await context.set_progress(progress, f"评估 {i + 1}/{total_questions}")

                # 执行查询
                query_result = await kb_instance.aquery(question_data["query"], db_id, **retrieval_config)

                # 处理结果
                if isinstance(query_result, dict):
                    generated_answer = query_result.get("answer", "")
                    retrieved_chunks = query_result.get("retrieved_chunks", [])
                else:
                    retrieved_chunks = query_result if isinstance(query_result, list) else []
                    generated_answer = ""

                # 如果没有生成的答案，但有检索结果且配置了 LLM，则生成答案
                if not generated_answer and retrieved_chunks and retrieval_config.get("answer_llm"):
                    logger.debug(f"使用 LLM {retrieval_config.get('answer_llm')} 生成答案...")
                    try:
                        # 从配置中获取 LLM
                        model_spec = retrieval_config["answer_llm"]
                        llm = select_model(model_spec=model_spec)

                        # 构建上下文
                        context_docs = []
                        for idx, chunk in enumerate(retrieved_chunks[:5]):  # 使用前5个最相关的文档
                            content = chunk.get("content", "")
                            if content:
                                context_docs.append(f"文档 {idx + 1}:\n{content}")

                        context_text = "\\n\\n".join(context_docs)

                        # 构建提示词
                        prompt = (
                            f"基于以下上下文信息，请回答用户的问题。\n\n"
                            f"上下文信息：{context_text}\n\n"
                            f"用户问题：{question_data["query"]}\n\n"
                            "请根据上下文信息准确回答问题。如果上下文中没有相关信息，请说明。\n\n"
                        )

                        # 生成答案 - 使用 asyncio.to_thread 避免阻塞事件循环
                        response = await asyncio.to_thread(llm.call, prompt, stream=False)
                        generated_answer = response.content if response else ""
                        logger.debug(f"LLM 生成的答案长度: {len(generated_answer) if generated_answer else 0}")

                    except Exception as e:
                        logger.error(f"LLM 生成答案失败: {e}")
                        generated_answer = ""

                # 计算指标
                current_metrics = {}
                retrieval_scores = {}
                answer_scores = {}

                if benchmark_meta.get("has_gold_chunks") and question_data.get("gold_chunk_ids"):
                    retrieval_scores = EvaluationMetricsCalculator.calculate_retrieval_metrics(
                        retrieved_chunks, question_data["gold_chunk_ids"]
                    )
                    current_metrics.update(retrieval_scores)
                    all_retrieval_metrics.append(retrieval_scores)

                if benchmark_meta.get("has_gold_answers") and question_data.get("gold_answer"):
                    if judge_llm:
                        # 评判过程包含 LLM 调用，使用 asyncio.to_thread 避免阻塞
                        answer_scores = await asyncio.to_thread(
                            EvaluationMetricsCalculator.calculate_answer_metrics,
                            query=question_data["query"],
                            generated_answer=generated_answer,
                            gold_answer=question_data["gold_answer"],
                            judge_llm=judge_llm,
                        )
                        current_metrics.update(answer_scores)
                        all_answer_metrics.append(answer_scores)
                    else:
                        logger.warning("需要计算答案指标但未配置 Judge LLM")

                interim_results.append(
                    {
                        "query": question_data["query"],
                        "gold_chunk_ids": question_data.get("gold_chunk_ids"),
                        "gold_answer": question_data.get("gold_answer"),
                        "generated_answer": generated_answer,
                        "retrieved_chunks": retrieved_chunks,
                        "metrics": current_metrics,
                    }
                )

                # 计算当前累计指标
                current_overall_metrics = {}
                if all_retrieval_metrics:
                    keys = all_retrieval_metrics[0].keys()
                    for k in keys:
                        current_overall_metrics[k] = sum(m.get(k, 0) for m in all_retrieval_metrics) / len(
                            all_retrieval_metrics
                        )
                if all_answer_metrics:
                    scores = [m.get("score", 0) for m in all_answer_metrics]
                    current_overall_metrics["answer_correctness"] = sum(scores) / len(scores) if scores else 0.0

                # 更新 Tasker 的 result 以便实时获取当前指标
                await context.set_result(
                    {
                        "current_metrics": current_overall_metrics,
                        "completed_questions": i + 1,
                        "total_questions": total_questions,
                    }
                )

                # 定期更新文件 (每5个或最后一个)
                if (i + 1) % 5 == 0 or (i + 1) == total_questions:
                    update_result_file(completed=i + 1, interim=interim_results)

            # 最终计算
            await context.set_progress(95, "计算最终指标")

            # 汇总指标
            overall_metrics = {}

            # 检索指标平均值
            if all_retrieval_metrics:
                keys = all_retrieval_metrics[0].keys()
                for k in keys:
                    overall_metrics[k] = sum(m.get(k, 0) for m in all_retrieval_metrics) / len(all_retrieval_metrics)

            # 答案指标平均值
            if all_answer_metrics:
                scores = [m.get("score", 0) for m in all_answer_metrics]
                overall_metrics["answer_correctness"] = sum(scores) / len(scores) if scores else 0.0

            overall_score = EvaluationMetricsCalculator.calculate_overall_score(
                all_retrieval_metrics, all_answer_metrics
            )
            overall_metrics["overall_score"] = overall_score

            update_result_file(
                status="completed",
                completed=total_questions,
                metrics=overall_metrics,
                interim=interim_results,
                final_score=overall_score,
            )
            await context.set_progress(100, "完成")

        except Exception as e:
            logger.error(f"Task failed: {e}")
            # Try to update status to failed
            try:
                # Need to find the file path again or pass it around.
                # Re-deriving from payload if available
                if "payload" in locals():
                    path = os.path.join(self._get_result_dir(payload["db_id"]), f"{payload['task_id']}.json")
                    if os.path.exists(path):
                        with open(path, encoding="utf-8") as f:
                            d = json.load(f)
                        d["status"] = "failed"
                        d["error"] = str(e)
                        with open(path, "w", encoding="utf-8") as f:
                            json.dump(d, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Error updating result file: {e}")
                pass

            await context.set_message(f"Error: {str(e)}")
            raise

    async def get_evaluation_results(self, task_id: str) -> dict[str, Any]:
        """获取评估结果"""
        try:
            # 使用优化的查找方法
            _, result_file_path = self._find_result_location(task_id)

            with open(result_file_path, encoding="utf-8") as f:
                return json.load(f)
        except ValueError:
            # 可能是内存中的任务状态？如果文件没创建（极早失败），检查 tasker
            task = await tasker.get_task(task_id)
            if task:
                return {"task_id": task_id, "status": task.status, "progress": task.progress, "message": task.message}
            raise ValueError(f"Result not found for task {task_id}")

    async def get_evaluation_history(self, db_id: str) -> list[dict[str, Any]]:
        """获取知识库的评估历史记录"""
        try:
            result_dir = self._get_result_dir(db_id)
            history = []

            # 查找所有 .json 文件
            result_files = glob.glob(os.path.join(result_dir, "*.json"))
            for result_file in result_files:
                try:
                    with open(result_file, encoding="utf-8") as f:
                        data = json.load(f)
                        # 只返回摘要信息，不返回详细的interim_results
                        summary = {
                            "task_id": data.get("task_id"),
                            "benchmark_id": data.get("benchmark_id"),
                            "status": data.get("status"),
                            "started_at": data.get("started_at"),
                            "completed_at": data.get("completed_at"),
                            "total_questions": data.get("total_questions"),
                            "completed_questions": data.get("completed_questions"),
                            "overall_score": data.get("overall_score"),
                            # 包含检索配置
                            "retrieval_config": data.get("retrieval_config", {}),
                            # 也可以带上部分 metrics 摘要
                            "metrics": data.get("metrics"),
                        }
                        history.append(summary)
                except Exception as e:
                    logger.error(f"Failed to load result file {result_file}: {e}")

            # 按开始时间倒序
            history.sort(key=lambda x: x.get("started_at", ""), reverse=True)
            return history

        except Exception as e:
            logger.error(f"获取评估历史失败: {e}")
            raise
