import asyncio
import glob
import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

from server.services.tasker import TaskContext, tasker
from src.knowledge import knowledge_base
from src.models import select_model
from src.utils import logger
from src.utils.evaluation_metrics import EvaluationMetricsCalculator


class EvaluationService:
    """RAG评估服务"""

    def __init__(self):
        pass

    def _get_benchmark_dir(self, db_id: str) -> str:
        kb_instance = knowledge_base.get_kb(db_id)
        base_dir = os.path.join(kb_instance.work_dir, db_id)
        path = os.path.join(base_dir, "benchmarks")
        os.makedirs(path, exist_ok=True)
        return path

    def _get_result_dir(self, db_id: str) -> str:
        kb_instance = knowledge_base.get_kb(db_id)
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
            benchmark_dir = self._get_benchmark_dir(db_id)

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
            kb_instance = knowledge_base.get_kb(db_id)
            if db_id not in kb_instance.benchmarks_meta:
                kb_instance.benchmarks_meta[db_id] = {}
            kb_instance.benchmarks_meta[db_id][benchmark_id] = meta
            kb_instance._save_metadata()
            return meta

        except Exception as e:
            logger.error(f"上传评估基准失败: {e}")
            raise

    async def get_benchmarks(self, db_id: str) -> list[dict[str, Any]]:
        """获取知识库的评估基准列表"""
        try:
            kb_instance = knowledge_base.get_kb(db_id)
            benchmarks_map = kb_instance.benchmarks_meta.get(db_id, {})
            benchmarks = list(benchmarks_map.values())
            benchmarks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return benchmarks

        except Exception as e:
            logger.error(f"获取评估基准列表失败: {e}")
            raise

    async def get_benchmark_detail(self, benchmark_id: str) -> dict[str, Any]:
        """获取评估基准详情 (包含问题列表)"""
        try:
            for kb_instance in knowledge_base.kb_instances.values():
                for db_id, m in kb_instance.benchmarks_meta.items():
                    if benchmark_id in m:
                        meta = m[benchmark_id]
                        data_file_path = meta.get("benchmark_file")
                        questions = []
                        if data_file_path and os.path.exists(data_file_path):
                            with open(data_file_path, encoding="utf-8") as f:
                                for line in f:
                                    if line.strip():
                                        questions.append(json.loads(line))
                        meta_with_q = meta.copy()
                        meta_with_q["questions"] = questions
                        return meta_with_q
            raise ValueError("Benchmark not found")

        except Exception as e:
            logger.error(f"获取评估基准详情失败: {e}")
            raise

    async def get_benchmark_detail_by_db(
        self, db_id: str, benchmark_id: str, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        """根据 db_id 获取评估基准详情（支持分页）"""
        try:
            kb_instance = knowledge_base.get_kb(db_id)
            benchmarks_map = kb_instance.benchmarks_meta.get(db_id, {})
            if benchmark_id not in benchmarks_map:
                raise ValueError("Benchmark not found")
            meta = benchmarks_map[benchmark_id]
            data_file_path = meta.get("benchmark_file")

            # 获取总问题数和分页数据
            total_questions = meta.get("question_count", 0)
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

            meta_with_q = meta.copy()
            meta_with_q.update(
                {
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
            )
            return meta_with_q
        except Exception as e:
            logger.error(f"获取评估基准详情失败: {e}")
            raise

    async def delete_benchmark(self, benchmark_id: str) -> None:
        """删除评估基准"""
        try:
            # 在所有KB中查找并删除
            for kb_instance in knowledge_base.kb_instances.values():
                for db_id, m in list(kb_instance.benchmarks_meta.items()):
                    if benchmark_id in m:
                        meta = m[benchmark_id]
                        data_file_path = meta.get("benchmark_file")
                        if data_file_path and os.path.exists(data_file_path):
                            os.remove(data_file_path)
                        del kb_instance.benchmarks_meta[db_id][benchmark_id]
                        kb_instance._save_metadata()
                        logger.info(f"成功删除评估基准: {benchmark_id}")
                        return
            raise ValueError("Benchmark not found")

        except Exception as e:
            logger.error(f"删除评估基准失败: {e}")
            raise

    async def delete_evaluation_result(self, task_id: str) -> None:
        """删除评估结果"""
        raise ValueError("Endpoint requires db_id; use delete_evaluation_result_by_db")

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
        import math
        import random

        await context.set_progress(0, "初始化")

        task = context._tasker._tasks.get(context.task_id)
        payload = task.payload if task else {}

        db_id = payload.get("db_id")
        name = payload.get("name", "自动生成评估基准")
        description = payload.get("description", "")
        count = int(payload.get("count", 10))
        neighbors_count = int(payload.get("neighbors_count", 0))
        embedding_model_id = payload.get("embedding_model_id")
        llm_model_spec = payload.get("llm_model_spec") or (payload.get("llm_config") or {}).get("model_spec")

        if neighbors_count < 0:
            neighbors_count = 0
        if neighbors_count > 10:
            neighbors_count = 10

        kb_instance = knowledge_base.get_kb(db_id)
        if not kb_instance:
            await context.set_message("知识库不存在")
            raise ValueError("Knowledge Base not found")
        if kb_instance.kb_type == "lightrag":
            await context.set_message("暂不支持该类型知识库生成评估基准")
            raise ValueError("Unsupported KB type for benchmark generation")

        await context.set_progress(5, "加载chunks")

        all_chunks = []
        for fid, finfo in kb_instance.files_meta.items():
            if finfo.get("database_id") != db_id:
                continue
            try:
                content_info = await kb_instance.get_file_content(db_id, fid)
                lines = content_info.get("lines", [])
                for line in lines:
                    all_chunks.append(
                        {
                            "id": line.get("id"),
                            "content": line.get("content", ""),
                            "file_id": fid,
                            "chunk_index": line.get("chunk_order_index"),
                        }
                    )
            except Exception:
                continue

        if not all_chunks:
            await context.set_message("知识库为空或未解析到chunks")
            raise ValueError("No chunks found in knowledge base")

        contents = [c["content"] for c in all_chunks]

        await context.set_progress(15, "向量化")

        if not embedding_model_id:
            db_meta = kb_instance.databases_meta.get(db_id, {})
            embed_info = db_meta.get("embed_info", {})
            embedding_model_id = embed_info.get("name") or embed_info.get("model") or ""
        if not embedding_model_id:
            raise ValueError("Embedding model not specified")

        from src.models import select_embedding_model, select_model

        embed_model = select_embedding_model(embedding_model_id)
        # TODO: Performance Optimization
        # Currently, we re-calculate embeddings for ALL chunks in the KB for every benchmark generation.
        # This is inefficient for large KBs (O(N) embedding calls).
        # Optimization: Reuse existing embeddings from Vector DB if embedding_model_id matches the KB's embedding model.
        embeddings = await embed_model.abatch_encode(contents, batch_size=40)
        norms = [math.sqrt(sum(x * x for x in vec)) or 1.0 for vec in embeddings]

        def cosine(a, b, na, nb):
            s = 0.0
            for i in range(len(a)):
                s += a[i] * b[i]
            return s / (na * nb)

        llm = select_model(model_spec=llm_model_spec)

        benchmark_id = f"benchmark_{uuid.uuid4().hex[:8]}"
        bench_dir = self._get_benchmark_dir(db_id)
        data_file_path = os.path.join(bench_dir, f"{benchmark_id}.jsonl")

        generated = 0
        attempts = 0

        await context.set_progress(0, "准备生成样本")

        with open(data_file_path, "w", encoding="utf-8") as f:
            # Allow more attempts to generate enough questions
            max_attempts = max(count * 5, 50)
            while generated < count and attempts < max_attempts:
                attempts += 1
                i0 = random.randrange(len(all_chunks))
                e0 = embeddings[i0]
                n0 = norms[i0]

                sims = []
                for j in range(len(all_chunks)):
                    if j == i0:
                        continue
                    s = cosine(e0, embeddings[j], n0, norms[j])
                    sims.append((j, s))
                sims.sort(key=lambda x: x[1], reverse=True)
                top_js = [j for j, _ in sims[:neighbors_count]]

                ctx_items = []
                ctx_items.append((all_chunks[i0]["id"], all_chunks[i0]["content"]))
                for j in top_js:
                    ctx_items.append((all_chunks[j]["id"], all_chunks[j]["content"]))
                allowed_ids = {cid for cid, _ in ctx_items}
                context_text = "\n\n".join([f"片段ID={cid}\n{content}" for cid, content in ctx_items])

                prompt = (
                    "你将基于以下上下文生成一个可由上下文准确回答的问题与标准答案。"
                    "仅返回一个JSON对象，不要包含其他文字。"
                    "键为 query、gold_answer、gold_chunk_ids。gold_chunk_ids 必须是上述上下文片段的ID子集。\n\n"
                    "上下文：\n" + context_text + "\n"
                )

                try:
                    resp = await asyncio.to_thread(llm.call, prompt, False)
                    content = resp.content if resp else ""

                    import json_repair

                    obj = json_repair.loads(content)
                    q = obj.get("query")
                    a = obj.get("gold_answer")
                    gids = obj.get("gold_chunk_ids")
                    if not q or not a or not isinstance(gids, list):
                        logger.warning(f"Generated JSON missing fields or invalid format: {obj}")
                        continue

                    gids = [str(x) for x in gids if str(x) in allowed_ids]
                    if not gids:
                        logger.warning("Generated gold_chunk_ids not found in allowed context")
                        continue

                    line = {"query": q, "gold_chunk_ids": gids, "gold_answer": a}
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")
                    generated += 1
                    await context.set_progress(0 + int(99 * generated / max(count, 1)), f"已生成 {generated}/{count}")
                except Exception as e:
                    logger.warning(f"Benchmark generation failed for one item: {e}")
                    continue

        meta = {
            "id": benchmark_id,
            "benchmark_id": benchmark_id,
            "name": name,
            "description": description,
            "db_id": db_id,
            "question_count": generated,
            "has_gold_chunks": True,
            "has_gold_answers": True,
            "benchmark_file": data_file_path,
            "created_by": payload.get("created_by"),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        kb_instance = knowledge_base.get_kb(db_id)
        if db_id not in kb_instance.benchmarks_meta:
            kb_instance.benchmarks_meta[db_id] = {}
        kb_instance.benchmarks_meta[db_id][benchmark_id] = meta
        kb_instance._save_metadata()

        await context.set_progress(100, "完成")

    async def run_evaluation(
        self, db_id: str, benchmark_id: str, model_config: dict[str, Any] = None, created_by: str = "system"
    ) -> str:
        """运行RAG评估"""
        try:
            task_id = f"eval_{uuid.uuid4().hex[:8]}"

            kb_instance = knowledge_base.get_kb(db_id)
            bm = kb_instance.benchmarks_meta.get(db_id, {}).get(benchmark_id)
            if not bm:
                raise ValueError("Benchmark not found")
            benchmark_meta = bm

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
            kb_instance = knowledge_base.get_kb(db_id)
            benchmark_meta = kb_instance.benchmarks_meta.get(db_id, {}).get(benchmark_id)
            if not benchmark_meta:
                raise ValueError("Benchmark not found")
            data_path = benchmark_meta.get("benchmark_file")
            if not data_path or not os.path.exists(data_path):
                raise ValueError("Benchmark file not found")

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
                            f"用户问题：{question_data['query']}\n\n"
                            "请根据上下文信息准确回答问题。\n\n"
                            "如果上下文中缺少相关信息，请回答“信息不足，无法回答”。\n\n"
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
        raise ValueError("Endpoint requires db_id; use get_evaluation_results_by_db")

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
        # 索引与回退逻辑已移除，统一通过 db_id 定位

    async def get_evaluation_results_by_db(
        self, db_id: str, task_id: str, page: int = 1, page_size: int = 20, error_only: bool = False
    ) -> dict[str, Any]:
        # Validate task_id format to prevent path traversal
        if not re.match(r"^eval_[a-f0-9]{8}$", task_id):
            raise ValueError("Invalid task_id format")
        result_file_path = os.path.join(self._get_result_dir(db_id), f"{task_id}.json")
        if not os.path.exists(result_file_path):
            task = await tasker.get_task(task_id)
            if task:
                return {
                    "task_id": task_id,
                    "status": task.status,
                    "progress": task.progress,
                    "message": task.message,
                }
            raise ValueError(f"Result not found for task {task_id}")

        # 加载JSON文件
        with open(result_file_path, encoding="utf-8") as f:
            data = json.load(f)

        # 如果是分页请求，处理详细结果
        if page and page_size:
            all_results = data.get("interim_results", data.get("results", []))

            # 如果只要错误结果，先过滤
            if error_only:
                filtered_results = []
                for item in all_results:
                    # 检查答案评分是否为错误（score <= 0.5）
                    if item.get("metrics", {}).get("score", 1.0) <= 0.5:
                        filtered_results.append(item)
                        continue

                    # 检查检索指标是否明显偏低
                    metrics = item.get("metrics", {})
                    has_low_recall = any(metrics.get(k, 1.0) < 0.3 for k in metrics if k.startswith("recall@"))
                    if has_low_recall:
                        filtered_results.append(item)
                all_results = filtered_results

            # 计算分页
            total = len(all_results)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paged_results = all_results[start_idx:end_idx]

            # 返回分页数据
            return {
                "task_id": data.get("task_id", task_id),
                "status": data.get("status"),
                "started_at": data.get("started_at"),
                "completed_at": data.get("completed_at"),
                "total_questions": data.get("total_questions", 0),
                "completed_questions": data.get("completed_questions", 0),
                "overall_score": data.get("overall_score"),
                "retrieval_config": data.get("retrieval_config"),
                "interim_results": paged_results,
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size,
                    "error_only": error_only,
                },
            }

        # 非分页请求，返回完整数据（保持向后兼容）
        return data

    async def delete_evaluation_result_by_db(self, db_id: str, task_id: str) -> None:
        # Validate task_id format to prevent path traversal
        if not re.match(r"^eval_[a-f0-9]{8}$", task_id):
            raise ValueError("Invalid task_id format")
        result_file_path = os.path.join(self._get_result_dir(db_id), f"{task_id}.json")
        if os.path.exists(result_file_path):
            os.remove(result_file_path)
            logger.info(f"成功删除评估结果: {task_id}")
            return
        raise ValueError("Result not found")
