import asyncio

import httpx


async def delete_agent(client: httpx.AsyncClient, headers: dict[str, str], slug: str) -> None:
    """等待 Agent 执行收敛后删除测试定义。"""
    async with asyncio.timeout(30):
        while True:
            response = await client.delete(f"/api/agent/{slug}", headers=headers)
            if response.status_code != 409 or response.json().get("detail") != "智能体仍有活跃执行或待处理输入":
                assert response.status_code in {200, 404}, response.text
                return
            await asyncio.sleep(0.2)
