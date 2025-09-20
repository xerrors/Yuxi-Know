"""
对话API测试
测试智能体对话、线程管理等相关接口
"""

import pytest
import httpx
import json


class TestChatAPI:
    """对话API测试类"""

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_get_default_agent(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试获取默认智能体"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        response = await test_client.get("/api/chat/default_agent", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "default_agent_id" in data
            print(f"Default agent ID: {data['default_agent_id']}")
        else:
            print(f"Get default agent failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_get_agents(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试获取智能体列表"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        response = await test_client.get("/api/chat/agent", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "agents" in data
            assert isinstance(data["agents"], list)
            print(f"Found {len(data['agents'])} agents")
            if data["agents"]:
                agent = data["agents"][0]
                print(f"First agent: {agent}")
        else:
            print(f"Get agents failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_simple_call(self, test_client: httpx.AsyncClient, auth_headers: dict, test_query: str):
        """测试简单对话调用"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        call_data = {"query": test_query, "meta": {"test": True}}

        response = await test_client.post("/api/chat/call", json=call_data, headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "response" in data
            assert isinstance(data["response"], str)
            print(f"Chat response: {data['response'][:100]}...")
        else:
            # 安全地处理响应
            try:
                error_data = response.json()
                print(f"Simple call failed with status {response.status_code}: {error_data}")
            except Exception:
                print(f"Simple call failed with status {response.status_code}: {response.text[:200]}...")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_unauthorized_chat_access(self, test_client: httpx.AsyncClient):
        """测试未授权访问对话接口"""
        # 测试简单调用
        response = await test_client.post("/api/chat/call", json={"query": "test"})
        assert response.status_code == 401

        # 测试获取智能体
        response = await test_client.get("/api/chat/agent")
        assert response.status_code == 401

        # 测试获取默认智能体
        response = await test_client.get("/api/chat/default_agent")
        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.auth
    @pytest.mark.slow
    async def test_agent_chat_streaming(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试智能体流式对话"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        # 首先获取可用的智能体
        agents_response = await test_client.get("/api/chat/agent", headers=auth_headers)

        if agents_response.status_code != 200:
            pytest.skip("Cannot get agents list, skipping agent chat test")

        agents_data = agents_response.json()
        if not agents_data.get("agents"):
            pytest.skip("No agents available, skipping agent chat test")

        agent_id = agents_data["agents"][0].get("id")
        if not agent_id:
            pytest.skip("No valid agent ID found, skipping agent chat test")

        # 测试智能体对话
        chat_data = {"query": "Hello, this is a test message", "config": {"test": True}, "meta": {"test": True}}

        response = await test_client.post(f"/api/chat/agent/{agent_id}", json=chat_data, headers=auth_headers)

        if response.status_code == 200:
            # 处理流式响应
            content = await response.aread()
            lines = content.decode("utf-8").strip().split("\n")

            # 验证流式响应格式
            for i, line in enumerate(lines[:3]):  # 只检查前几行
                try:
                    json_data = json.loads(line)
                    assert "status" in json_data
                    print(f"Stream line {i}: status={json_data.get('status')}")
                except json.JSONDecodeError:
                    print(f"Invalid JSON in line {i}: {line[:50]}...")

            print(f"Received {len(lines)} stream lines from agent {agent_id}")
        else:
            print(f"Agent chat failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_create_thread(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试创建对话线程"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        # 获取可用的智能体
        agents_response = await test_client.get("/api/chat/agent", headers=auth_headers)

        if agents_response.status_code != 200:
            pytest.skip("Cannot get agents list, skipping thread test")

        agents_data = agents_response.json()
        if not agents_data.get("agents"):
            pytest.skip("No agents available, skipping thread test")

        agent_id = agents_data["agents"][0].get("id")
        if not agent_id:
            pytest.skip("No valid agent ID found, skipping thread test")

        # 创建线程
        thread_data = {"title": "测试对话线程", "agent_id": agent_id, "description": "这是一个测试创建的对话线程"}

        response = await test_client.post("/api/chat/thread", json=thread_data, headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "id" in data
            assert data["agent_id"] == agent_id
            assert data["title"] == thread_data["title"]
            print(f"Created thread: {data['id']}")

            # 测试获取线程列表
            threads_response = await test_client.get(f"/api/chat/threads?agent_id={agent_id}", headers=auth_headers)

            if threads_response.status_code == 200:
                threads_data = threads_response.json()
                assert isinstance(threads_data, list)
                # 验证我们创建的线程在列表中
                thread_ids = [t["id"] for t in threads_data]
                assert data["id"] in thread_ids
                print(f"Found {len(threads_data)} threads for agent {agent_id}")

                # 清理：删除创建的线程
                delete_response = await test_client.delete(f"/api/chat/thread/{data['id']}", headers=auth_headers)
                if delete_response.status_code == 200:
                    print(f"Successfully deleted thread {data['id']}")

        else:
            print(f"Create thread failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_get_tools(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试获取工具列表"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        # 获取可用的智能体
        agents_response = await test_client.get("/api/chat/agent", headers=auth_headers)

        if agents_response.status_code != 200:
            pytest.skip("Cannot get agents list, skipping tools test")

        agents_data = agents_response.json()
        if not agents_data.get("agents"):
            pytest.skip("No agents available, skipping tools test")

        agent_id = agents_data["agents"][0].get("id")
        if not agent_id:
            pytest.skip("No valid agent ID found, skipping tools test")

        response = await test_client.get(f"/api/chat/tools?agent_id={agent_id}", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "tools" in data
            assert isinstance(data["tools"], dict)
            print(f"Found {len(data['tools'])} tools for agent {agent_id}")
            if data["tools"]:
                tool_names = list(data["tools"].keys())
                print(f"Available tools: {tool_names[:5]}...")  # 显示前5个工具名
        else:
            print(f"Get tools failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_agent_config(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试智能体配置获取"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        # 获取可用的智能体
        agents_response = await test_client.get("/api/chat/agent", headers=auth_headers)

        if agents_response.status_code != 200:
            pytest.skip("Cannot get agents list, skipping config test")

        agents_data = agents_response.json()
        if not agents_data.get("agents"):
            pytest.skip("No agents available, skipping config test")

        agent_id = agents_data["agents"][0].get("id")
        if not agent_id:
            pytest.skip("No valid agent ID found, skipping config test")

        response = await test_client.get(f"/api/chat/agent/{agent_id}/config", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert "config" in data
            print(f"Agent {agent_id} config keys: {list(data['config'].keys()) if data['config'] else 'None'}")
        else:
            print(f"Get agent config failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_thread_management_full_cycle(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试完整的线程管理周期：创建、更新、删除"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        # 获取智能体
        agents_response = await test_client.get("/api/chat/agent", headers=auth_headers)
        if agents_response.status_code != 200:
            pytest.skip("Cannot get agents list")

        agents_data = agents_response.json()
        if not agents_data.get("agents"):
            pytest.skip("No agents available")

        agent_id = agents_data["agents"][0].get("id")
        if not agent_id:
            pytest.skip("No valid agent ID found")

        # 1. 创建线程
        thread_data = {"title": "完整测试线程", "agent_id": agent_id, "description": "用于完整周期测试的线程"}

        create_response = await test_client.post("/api/chat/thread", json=thread_data, headers=auth_headers)
        assert create_response.status_code == 200
        thread = create_response.json()
        thread_id = thread["id"]

        # 2. 更新线程
        update_data = {"title": "更新后的标题", "description": "更新后的描述"}

        update_response = await test_client.put(f"/api/chat/thread/{thread_id}", json=update_data, headers=auth_headers)

        if update_response.status_code == 200:
            updated_thread = update_response.json()
            assert updated_thread["title"] == update_data["title"]
            assert updated_thread["description"] == update_data["description"]
            print(f"Successfully updated thread {thread_id}")

        # 3. 删除线程
        delete_response = await test_client.delete(f"/api/chat/thread/{thread_id}", headers=auth_headers)

        if delete_response.status_code == 200:
            print(f"Successfully deleted thread {thread_id}")

            # 验证线程确实被删除（不应该再出现在列表中）
            threads_response = await test_client.get(f"/api/chat/threads?agent_id={agent_id}", headers=auth_headers)

            if threads_response.status_code == 200:
                threads_data = threads_response.json()
                thread_ids = [t["id"] for t in threads_data]
                assert thread_id not in thread_ids
                print("Confirmed thread deletion")


# 标记为集成测试
pytestmark = [pytest.mark.integration]
