import requests
import json
import time
import sys
import os


# 添加评估指标测试功能
def test_evaluation_metrics():
    """测试评估指标计算"""
    print("\n" + "=" * 50)
    print("测试评估指标计算")
    print("=" * 50)

    try:
        from src.utils.evaluation_metrics import EvaluationMetricsCalculator

        # 测试检索指标
        retrieved_chunks = [
            {"content": "test1", "metadata": {"chunk_id": "file_bbb147_chunk_0"}},
            {"content": "test2", "metadata": {"chunk_id": "file_bbb147_chunk_1"}},
            {"content": "test3", "metadata": {"chunk_id": "file_bbb147_chunk_2"}},
        ]
        gold_chunk_ids = ["file_bbb147_chunk_0", "file_bbb147_chunk_2"]

        print("测试检索指标...")
        retrieval_metrics = EvaluationMetricsCalculator.calculate_retrieval_metrics(retrieved_chunks, gold_chunk_ids)
        print(f"检索指标结果: {retrieval_metrics}")

        # 测试答案指标
        # generated_answer = "该研究以数据语义化—知识结构化—可信推理的技术主线"
        # gold_answer = "该研究以数据语义化—知识结构化—可信推理的技术主线，遵循数据—知识—推理—应用的演化逻辑"

        print("\n测试答案指标（需要Judge LLM，跳过实际LLM调用）...")
        # 由于需要judge_llm，这里只测试检索指标
        print("跳过答案指标测试（需要配置Judge LLM）")

        print("评估指标计算测试完成！")
        return True

    except Exception as e:
        print(f"评估指标测试失败: {e}")
        return False


BASE_URL = "http://localhost:5050"
USERNAME = "zwj"
PASSWORD = "zwj12138"
DB_ID = "kb_5e343066eb4713959698ae6ca16843a0"


def get_token():
    try:
        resp = requests.post(f"{BASE_URL}/api/auth/token", data={"username": USERNAME, "password": PASSWORD})
        if resp.status_code != 200:
            print(f"Login failed: {resp.text}")
            return None
        return resp.json()["access_token"]
    except Exception as e:
        print(f"Connection failed: {e}")
        return None


def main():
    # 首先测试评估指标计算
    test_evaluation_metrics()

    token = get_token()
    if not token:
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    print(f"\n1. Trying to retrieve a real chunk from {DB_ID}...")

    chunk_content = "This is a fallback test query."
    chunk_id = "unknown"

    try:
        # 尝试查询 (Fixed payload structure)
        resp = requests.post(
            f"{BASE_URL}/api/knowledge/databases/{DB_ID}/query",
            headers=headers,
            json={"query": "人工智能", "meta": {"top_k": 5}},
        )

        if resp.status_code == 200:
            data = resp.json()
            # 结果在 result 字段中
            results = data.get("result", [])

            first_chunk = None
            if isinstance(results, list) and len(results) > 0:
                first_chunk = results[0]
            elif isinstance(results, dict) and "retrieved_chunks" in results:
                if results["retrieved_chunks"]:
                    first_chunk = results["retrieved_chunks"][0]

            if first_chunk:
                print(f"Found chunk: {str(first_chunk.get('content', ''))[:50]}...")
                chunk_content = first_chunk.get("content", chunk_content)
                chunk_id = first_chunk.get("chunk_id", chunk_id) or first_chunk.get("id", chunk_id)
            else:
                print("No chunks found in retrieval results. Using fallback.")
                print(f"Raw results: {results}")
        else:
            print(f"Query failed: {resp.text}")

    except Exception as e:
        print(f"Query Exception: {e}")

    print(f"\n2. Creating benchmark with query based on chunk: {chunk_id}")

    # 构造 Benchmark 数据
    benchmark_data = {
        "query": chunk_content,  # 使用 Chunk 内容作为查询，理论上应该能召回它自己
        "gold_chunk_ids": [str(chunk_id)],  # Ensure string
        "gold_answer": "This is a gold answer.",
    }

    # 生成临时文件
    with open("temp_benchmark.jsonl", "w") as f:
        f.write(json.dumps(benchmark_data, ensure_ascii=False) + "\n")

    print("\n3. Uploading benchmark...")
    try:
        files = {"file": ("temp_benchmark.jsonl", open("temp_benchmark.jsonl", "rb"), "application/jsonlines")}
        # Fixed: use params for name/description
        params = {"name": "Manual Eval Test", "description": "Test generated from script"}

        resp = requests.post(
            f"{BASE_URL}/api/evaluation/databases/{DB_ID}/benchmarks/upload",
            headers=headers,
            params=params,
            files=files,
        )

        if resp.status_code != 200:
            print(f"Upload failed: {resp.text}")
            sys.exit(1)

        benchmark = resp.json()
        # Benchmark response format depends on Service impl.
        # My filesystem impl returns the metadata dict directly.
        # But wait, KnowledgeRouter might wrap it?
        # router returns: return {"message": "上传成功", "data": result} (Assume standard wrapper)
        # Let's check router impl.

        # From router code read earlier:
        # result = await service.upload_benchmark(...)
        # return {"message": "上传成功", "data": result}

        benchmark_id = benchmark["data"]["benchmark_id"]
        print(f"Benchmark uploaded: {benchmark_id}")

    except Exception as e:
        print(f"Upload Exception: {e}")
        sys.exit(1)

    print("\n4. Running evaluation...")
    try:
        payload = {"benchmark_id": benchmark_id, "retrieval_config": {"top_k": 5}}

        resp = requests.post(f"{BASE_URL}/api/evaluation/databases/{DB_ID}/run", headers=headers, json=payload)

        if resp.status_code != 200:
            print(f"Run evaluation failed: {resp.text}")
            sys.exit(1)

        task_id = resp.json()["data"]["task_id"]
        print(f"Evaluation task started: {task_id}")

        # 轮询状态
        while True:
            resp = requests.get(f"{BASE_URL}/api/evaluation/{task_id}/progress", headers=headers)
            if resp.status_code != 200:
                print(f"Get progress failed: {resp.text}")
                break

            progress = resp.json()
            # The progress endpoint returns {task_id, status, ...} based on my service impl?
            # Router wrapper: return {"message": "success", "data": result}

            data = progress.get("data", progress)  # Handle wrapper if exists
            status = data["status"]
            current_progress = data.get("progress", 0)

            print(f"Status: {status}, Progress: {current_progress}%")

            if status in ["completed", "failed"]:
                break

            time.sleep(2)

        if status == "completed":
            print("\nEvaluation Completed!")
            # 获取结果
            resp = requests.get(f"{BASE_URL}/api/evaluation/{task_id}/results", headers=headers)
            print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        else:
            print("\nEvaluation Failed!")

    except Exception as e:
        print(f"Evaluation Exception: {e}")

    # 清理
    if os.path.exists("temp_benchmark.jsonl"):
        os.remove("temp_benchmark.jsonl")


if __name__ == "__main__":
    main()
