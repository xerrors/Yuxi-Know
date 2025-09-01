import asyncio
import time

import aiohttp


async def make_request(session: aiohttp.ClientSession, request_id: int) -> dict:
    """发送单个请求到API"""
    url = "http://localhost:5000/chat/call"
    payload = {"query": "写一个冒泡排序", "meta": {}}

    start_time = time.time()
    print(f"请求 {request_id} 开始时间: {time.strftime('%H:%M:%S', time.localtime(start_time))}")
    try:
        async with session.post(url, json=payload) as response:
            result = await response.json()
            print(f"请求 {request_id} 结果: {result}")
            end_time = time.time()
            duration = end_time - start_time
            print(
                f"请求 {request_id} 完成时间: "
                f"{time.strftime('%H:%M:%S', time.localtime(end_time))} "
                f"(耗时: {duration:.2f}秒)"
            )
            return {
                "request_id": request_id,
                "status": response.status,
                "time": duration,
                "start_time": start_time,
                "end_time": end_time,
                "success": True,
            }
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        print(
            f"请求 {request_id} 失败时间: "
            f"{time.strftime('%H:%M:%S', time.localtime(end_time))} "
            f"(耗时: {duration:.2f}秒)"
        )
        return {
            "request_id": request_id,
            "status": None,
            "time": duration,
            "start_time": start_time,
            "end_time": end_time,
            "success": False,
            "error": str(e),
        }


async def run_concurrent_test(num_requests: int = 10) -> list[dict]:
    """运行并发测试"""
    async with aiohttp.ClientSession() as session:
        tasks = [make_request(session, i) for i in range(num_requests)]
        return await asyncio.gather(*tasks)


def analyze_results(results: list[dict]) -> None:
    """分析并打印测试结果"""
    total_requests = len(results)
    successful_requests = sum(1 for r in results if r["success"])
    failed_requests = total_requests - successful_requests

    response_times = [r["time"] for r in results if r["success"]]
    if response_times:
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
    else:
        avg_time = max_time = min_time = 0

    print("\n=== 并发测试结果 ===")
    print(f"总请求数: {total_requests}")
    print(f"成功请求: {successful_requests}")
    print(f"失败请求: {failed_requests}")
    print(f"平均响应时间: {avg_time:.2f} 秒")
    print(f"最长响应时间: {max_time:.2f} 秒")
    print(f"最短响应时间: {min_time:.2f} 秒")

    if failed_requests > 0:
        print("\n失败的请求:")
        for result in results:
            if not result["success"]:
                print(f"请求 ID {result['request_id']}: {result.get('error', '未知错误')}")

    # 添加请求时间线分析
    print("\n=== 请求时间线分析 ===")
    sorted_results = sorted(results, key=lambda x: x["start_time"])
    test_start_time = sorted_results[0]["start_time"]
    test_end_time = sorted_results[-1]["end_time"]
    print(f"测试开始时间: {time.strftime('%H:%M:%S', time.localtime(test_start_time))}")
    print(f"测试结束时间: {time.strftime('%H:%M:%S', time.localtime(test_end_time))}")

    print("\n时间线详情:")
    print("请求ID  开始时间    结束时间    耗时(秒)  重叠请求数")
    active_requests = []

    for result in sorted_results:
        # 计算当前时间点的活跃请求数
        start_time = result["start_time"]
        end_time = result["end_time"]

        # 清理已完成的请求
        active_requests = [t for t in active_requests if t > start_time]
        active_requests.append(end_time)

        print(
            f"{result['request_id']:^7} "
            f"{time.strftime('%H:%M:%S', time.localtime(start_time))} "
            f"{time.strftime('%H:%M:%S', time.localtime(end_time))} "
            f"{result['time']:^8.2f}  {len(active_requests):^6}"
        )

    # 计算最大并发数
    max_concurrent = 0
    timeline = []
    for r in results:
        timeline.append((r["start_time"], 1))
        timeline.append((r["end_time"], -1))

    timeline.sort(key=lambda x: x[0])
    current_concurrent = 0
    for _, change in timeline:
        current_concurrent += change
        max_concurrent = max(max_concurrent, current_concurrent)

    print(f"\n最大并发请求数: {max_concurrent}")


if __name__ == "__main__":
    NUM_REQUESTS = 100  # 设置并发请求数

    print(f"开始运行 {NUM_REQUESTS} 个并发请求的测试...")
    results = asyncio.run(run_concurrent_test(NUM_REQUESTS))
    analyze_results(results)
