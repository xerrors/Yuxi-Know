"""
pytest配置文件和公共fixtures
提供测试环境配置和公共的测试工具
"""

import os
import pytest
import pytest_asyncio
import httpx
from collections.abc import AsyncGenerator
from dotenv import load_dotenv

# 加载测试环境变量
load_dotenv("test/.env.test")

# 测试配置
TEST_BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:5050")
TEST_USERNAME = os.getenv("TEST_USERNAME", "zwj")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "zwj12138")


@pytest_asyncio.fixture(scope="function")
async def test_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """创建异步HTTP客户端"""
    timeout = httpx.Timeout(30.0, connect=5.0)
    async with httpx.AsyncClient(base_url=TEST_BASE_URL, timeout=timeout, follow_redirects=True) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def auth_token(test_client: httpx.AsyncClient) -> str:
    """获取认证令牌用于需要认证的测试"""
    try:
        # 尝试登录获取token
        login_data = {"username": TEST_USERNAME, "password": TEST_PASSWORD}
        response = await test_client.post("/api/auth/token", data=login_data)

        if response.status_code == 200:
            data = response.json()
            return data.get("access_token", "")
        else:
            # 如果登录失败，返回空token，某些测试可能不需要认证
            print(f"Login failed with status {response.status_code}, continuing without auth token")
            return ""
    except Exception as e:
        print(f"Auth setup failed: {e}, continuing without auth token")
        return ""


@pytest_asyncio.fixture
async def auth_headers(auth_token: str) -> dict:
    """返回包含认证信息的headers"""
    if auth_token:
        return {"Authorization": f"Bearer {auth_token}"}
    return {}


@pytest.fixture
def test_query():
    """测试用的简单查询"""
    return "你好，这是一个测试查询"


@pytest.fixture
def test_chat_payload(test_query: str):
    """测试对话的请求负载"""
    return {"query": test_query, "meta": {"test": True}}


# pytest配置选项
def pytest_configure(config):
    """pytest配置"""
    config.addinivalue_line("markers", "auth: marks tests that require authentication")
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")


# 设置异步模式
pytest_plugins = ["pytest_asyncio"]

# 测试标记
pytest.mark.auth = pytest.mark.auth
pytest.mark.slow = pytest.mark.slow
pytest.mark.integration = pytest.mark.integration
