"""
测试附件上传和 agent state 获取的 API 脚本

使用方式:
    cd /home/zwj/workspace/Yuxi-Know
    docker compose exec api uv run python test/api/test_attachment_and_agent_state.py

或者本地运行:
    python test/api/test_attachment_and_agent_state.py
"""

import asyncio
import contextlib
import os
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")


# API 配置
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5050")

# 测试账户配置
USERNAME = os.getenv("YUXI_SUPER_ADMIN_NAME", "zwj")
PASSWORD = os.getenv("YUXI_SUPER_ADMIN_PASSWORD", "zwj12138")

# 默认 Agent ID (需要根据实际情况修改，使用类名)
DEFAULT_AGENT_ID = "ChatbotAgent"


class APITester:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.token: str | None = None
        self.user_id: str | None = None
        self.headers: dict | None = None

    @contextlib.asynccontextmanager
    async def _client(self, timeout: float = 30.0):
        """获取 HTTP 客户端"""
        client = httpx.AsyncClient(timeout=timeout)
        try:
            yield client
        finally:
            await client.aclose()

    async def login(self) -> bool:
        """登录获取 token"""
        print(f"\n{'=' * 60}")
        print(f"1. 正在登录: {self.username}")
        print(f"{'=' * 60}")

        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/api/auth/token",
                data={"username": self.username, "password": self.password},
            )

        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.user_id = str(data.get("user_id"))
            self.headers = {"Authorization": f"Bearer {self.token}"}
            print(f"   ✓ 登录成功! user_id: {self.user_id}")
            print(f"   ✓ Token: {self.token[:50]}...")
            return True
        else:
            print(f"   ✗ 登录失败: {response.status_code} - {response.text}")
            return False

    async def create_thread(self, agent_id: str) -> str:
        """创建对话线程"""
        print(f"\n{'=' * 60}")
        print(f"2. 创建对话线程 (agent_id: {agent_id})")
        print(f"{'=' * 60}")

        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/api/chat/thread",
                json={"agent_id": agent_id, "title": "API 测试对话"},
                headers=self.headers,
            )

        if response.status_code == 200:
            thread = response.json()
            thread_id = thread.get("id")
            print(f"   ✓ 创建成功! thread_id: {thread_id}")
            return thread_id
        else:
            print(f"   ✗ 创建失败: {response.status_code} - {response.text}")
            return ""

    async def upload_attachment(self, thread_id: str, file_path: str) -> dict | None:
        """上传附件"""
        print(f"\n{'=' * 60}")
        print(f"3. 上传附件: {file_path}")
        print(f"{'=' * 60}")

        if not os.path.exists(file_path):
            print(f"   ✗ 文件不存在: {file_path}")
            return None

        async with self._client(timeout=60.0) as client:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                response = await client.post(
                    f"{self.base_url}/api/chat/thread/{thread_id}/attachments",
                    files=files,
                    headers=self.headers,
                )

        if response.status_code == 200:
            attachment = response.json()
            print("   ✓ 上传成功!")
            print(f"      file_id: {attachment.get('file_id')}")
            print(f"      file_name: {attachment.get('file_name')}")
            print(f"      status: {attachment.get('status')}")
            return attachment
        else:
            print(f"   ✗ 上传失败: {response.status_code} - {response.text}")
            return None

    async def list_attachments(self, thread_id: str) -> list[dict]:
        """列出附件"""
        print(f"\n{'=' * 60}")
        print(f"4. 列出附件 (thread_id: {thread_id})")
        print(f"{'=' * 60}")

        async with self._client() as client:
            response = await client.get(
                f"{self.base_url}/api/chat/thread/{thread_id}/attachments",
                headers=self.headers,
            )

        if response.status_code == 200:
            data = response.json()
            attachments = data.get("attachments", [])
            print(f"   ✓ 获取到 {len(attachments)} 个附件:")
            for att in attachments:
                print(f"      - {att.get('file_name')}: {att.get('status')}")
            return attachments
        else:
            print(f"   ✗ 获取失败: {response.status_code} - {response.text}")
            return []

    async def get_agent_state(self, agent_id: str, thread_id: str) -> dict | None:
        """获取 agent state"""
        print(f"\n{'=' * 60}")
        print(f"5. 获取 Agent State (agent_id: {agent_id}, thread_id: {thread_id})")
        print(f"{'=' * 60}")

        async with self._client() as client:
            response = await client.get(
                f"{self.base_url}/api/chat/agent/{agent_id}/state",
                params={"thread_id": thread_id},
                headers=self.headers,
            )

        if response.status_code == 200:
            state = response.json()
            agent_state = state.get("agent_state", {})
            print("   ✓ 获取成功!")
            print(f"      files: {len(agent_state.get('files', {}))} 个")
            print(f"      todos: {len(agent_state.get('todos', []))} 个")
            if agent_state.get("files"):
                print("      文件列表:")
                for path in agent_state["files"]:
                    file_info = agent_state["files"][path]
                    print(f"         - {path}: {len(file_info.get('content', []))} 行")
            return state
        else:
            print(f"   ✗ 获取失败: {response.status_code} - {response.text}")
            return None

    async def send_chat_message(self, agent_id: str, thread_id: str, query: str) -> bool:
        """发送聊天消息（流式）"""
        print(f"\n{'=' * 60}")
        print("6. 发送聊天消息")
        print(f"{'=' * 60}")
        print(f"   Query: {query}")
        print(f"   Thread ID: {thread_id}")

        async with self._client(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat/agent/{agent_id}",
                json={"query": query, "config": {"thread_id": thread_id}},
                headers=self.headers,
            ) as response:
                print(f"\n   响应状态: {response.status_code}")
                print("   响应内容:")
                async for chunk in response.aiter_lines():
                    if chunk:
                        print(f"      {chunk[:150]}...")

                return response.status_code == 200


async def main():
    """主测试流程"""
    print("\n" + "=" * 60)
    print("   附件上传与 Agent State API 测试")
    print("=" * 60)
    print(f"\nAPI 地址: {API_BASE_URL}")
    print(f"测试账户: {USERNAME}")

    tester = APITester(API_BASE_URL, USERNAME, PASSWORD)

    # 1. 登录
    if not await tester.login():
        print("\n!!! 登录失败，测试终止 !!!")
        return

    # 2. 创建线程（使用默认 agent_id）
    agent_id = DEFAULT_AGENT_ID
    thread_id = await tester.create_thread(agent_id)
    if not thread_id:
        print("\n!!! 创建线程失败，测试终止 !!!")
        return

    # 3. 创建测试文件
    test_content = """# 测试文档

这是一个用于 API 测试的 Markdown 文件。

## 主要内容

- 第一点
- 第二点
- 第三点

```python
def hello():
    print("Hello, World!")
```
"""
    test_file_path = f"/tmp/test_attachment_{uuid.uuid4().hex[:8]}.md"
    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(test_content)
    print(f"\n   测试文件已创建: {test_file_path}")

    # 4. 上传附件
    attachment = await tester.upload_attachment(thread_id, test_file_path)

    # 5. 列出附件
    await tester.list_attachments(thread_id)

    # 6. 获取 agent state (验证附件是否在 state 中)
    if attachment:
        print("\n   等待后端处理...")
        await asyncio.sleep(2)
        await tester.get_agent_state(agent_id, thread_id)

    # 7. 发送聊天消息测试
    await tester.send_chat_message(agent_id, thread_id, "你好，请简单介绍一下你自己。")

    # 8. 再次获取 agent state (验证 todos 等状态)
    await asyncio.sleep(1)
    await tester.get_agent_state(agent_id, thread_id)

    # 清理测试文件
    if os.path.exists(test_file_path):
        os.remove(test_file_path)
        print(f"\n   测试文件已清理: {test_file_path}")

    print(f"\n{'=' * 60}")
    print("   测试完成!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
