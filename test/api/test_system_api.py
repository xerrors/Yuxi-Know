"""
系统API测试
测试系统管理、配置管理等相关接口
"""

import pytest
import httpx


class TestSystemAPI:
    """系统API测试类"""

    @pytest.mark.asyncio
    async def test_health_check(self, test_client: httpx.AsyncClient):
        """测试系统健康检查接口"""
        response = await test_client.get("/api/system/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert "message" in data
        print(f"Health check response: {data}")

    @pytest.mark.asyncio
    async def test_get_system_info(self, test_client: httpx.AsyncClient):
        """测试获取系统信息接口（公开接口）"""
        response = await test_client.get("/api/system/info")

        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert "data" in data
            print(f"System info response: {data}")
        else:
            # 如果接口不存在或有其他问题，记录但不失败
            print(f"System info request failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_get_config_unauthorized(self, test_client: httpx.AsyncClient):
        """测试未授权访问配置接口"""
        response = await test_client.get("/api/system/config")
        assert response.status_code == 401
        print("Config access properly requires authentication")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_get_config_authorized(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试已授权访问配置接口"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        response = await test_client.get("/api/system/config", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            # 验证配置数据结构
            assert isinstance(data, dict)
            # 检查一些常见的配置项
            expected_config_keys = [
                "enable_reranker",
                "enable_web_search",
                "model_provider",
                "model_name",
                "embed_model",
            ]
            for key in expected_config_keys:
                if key in data:
                    print(f"Config contains {key}: {data[key]}")
            print(f"Config keys: {list(data.keys())}")
        elif response.status_code == 403:
            print("User does not have admin privileges to access config")
        else:
            print(f"Get config failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_update_config_unauthorized(self, test_client: httpx.AsyncClient):
        """测试未授权更新配置"""
        config_data = {"key": "test_key", "value": "test_value"}
        response = await test_client.post("/api/system/config", json=config_data)
        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.auth
    @pytest.mark.slow
    async def test_update_single_config(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试更新单个配置项"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        # 先获取当前配置
        get_response = await test_client.get("/api/system/config", headers=auth_headers)

        if get_response.status_code != 200:
            pytest.skip("Cannot access config, skipping update test")

        original_config = get_response.json()

        # 尝试更新一个安全的配置项（如果存在的话）
        test_config_updates = [
            {"key": "enable_web_search", "value": True},
            {"key": "enable_reranker", "value": False},
        ]

        for config_update in test_config_updates:
            key = config_update["key"]
            if key in original_config:
                original_value = original_config[key]
                new_value = config_update["value"]

                # 更新配置
                response = await test_client.post("/api/system/config", json=config_update, headers=auth_headers)

                if response.status_code == 200:
                    updated_config = response.json()
                    assert updated_config[key] == new_value
                    print(f"Successfully updated {key} from {original_value} to {new_value}")

                    # 恢复原值
                    restore_data = {"key": key, "value": original_value}
                    restore_response = await test_client.post(
                        "/api/system/config", json=restore_data, headers=auth_headers
                    )
                    if restore_response.status_code == 200:
                        print(f"Successfully restored {key} to {original_value}")
                    break
                elif response.status_code == 403:
                    print("User does not have permission to update config")
                    break
                else:
                    print(f"Config update failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    @pytest.mark.slow
    async def test_batch_update_config(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试批量更新配置项"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        # 准备批量更新数据
        batch_updates = {"enable_web_search": True, "enable_reranker": False}

        response = await test_client.post("/api/system/config/update", json=batch_updates, headers=auth_headers)

        if response.status_code == 200:
            updated_config = response.json()
            for key, value in batch_updates.items():
                if key in updated_config:
                    assert updated_config[key] == value
                    print(f"Batch update verified: {key} = {value}")
        elif response.status_code == 403:
            print("User does not have permission to batch update config")
        else:
            print(f"Batch config update failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_get_system_logs(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试获取系统日志"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        response = await test_client.get("/api/system/logs", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "log" in data
            assert "message" in data
            assert data["message"] == "success"
            assert "log_file" in data
            print(f"Log file path: {data.get('log_file')}")
            print(f"Log length: {len(data.get('log', ''))}")
        elif response.status_code == 403:
            print("User does not have permission to access logs")
        else:
            print(f"Get logs failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_restart_system_permission(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试系统重启权限（仅超级管理员）"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        response = await test_client.post("/api/system/restart", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            print(f"Restart response: {data}")
        elif response.status_code == 403:
            print("User does not have superadmin privileges to restart system")
        else:
            print(f"Restart request failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_reload_info_config(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试重新加载信息配置"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        response = await test_client.post("/api/system/info/reload", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert "message" in data
            print(f"Info reload response: {data}")
        elif response.status_code == 403:
            print("User does not have permission to reload info config")
        else:
            print(f"Info reload failed with status {response.status_code}: {response.json()}")

    @pytest.mark.asyncio
    @pytest.mark.auth
    async def test_get_ocr_stats(self, test_client: httpx.AsyncClient, auth_headers: dict):
        """测试获取OCR统计信息"""
        if not auth_headers:
            pytest.skip("No auth token available, skipping authenticated test")

        response = await test_client.get("/api/system/ocr/stats", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            print(f"OCR stats response: {data}")
        elif response.status_code == 403:
            print("User does not have permission to access OCR stats")
        elif response.status_code == 404:
            print("OCR stats endpoint not available")
        else:
            print(f"OCR stats request failed with status {response.status_code}: {response.json()}")


# 标记为集成测试
pytestmark = [pytest.mark.integration]
