from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

AGENT_ENV_PATH = "/api/user/agent-env"


async def test_agent_env_requires_auth(test_client):
    response = await test_client.get(AGENT_ENV_PATH)
    assert response.status_code == 401


async def test_agent_env_round_trip_and_replace(test_client, standard_user):
    headers = standard_user["headers"]

    initial_response = await test_client.get(AGENT_ENV_PATH, headers=headers)
    assert initial_response.status_code == 200, initial_response.text
    assert initial_response.json()["env"] == {}

    payload = {"env": {"YUXI_TEST_TOKEN": "secret", "YUXI_EMPTY_VALUE": ""}}
    save_response = await test_client.put(AGENT_ENV_PATH, json=payload, headers=headers)
    assert save_response.status_code == 200, save_response.text
    assert save_response.json()["env"] == payload["env"]

    replace_response = await test_client.put(
        AGENT_ENV_PATH,
        json={"env": {"YUXI_TEST_TOKEN": "updated"}},
        headers=headers,
    )
    assert replace_response.status_code == 200, replace_response.text
    assert replace_response.json()["env"] == {"YUXI_TEST_TOKEN": "updated"}

    final_response = await test_client.get(AGENT_ENV_PATH, headers=headers)
    assert final_response.status_code == 200, final_response.text
    assert final_response.json()["env"] == {"YUXI_TEST_TOKEN": "updated"}


async def test_agent_env_rejects_invalid_keys(test_client, standard_user):
    response = await test_client.put(
        AGENT_ENV_PATH,
        json={"env": {"INVALID-KEY": "value"}},
        headers=standard_user["headers"],
    )
    assert response.status_code == 400


async def test_agent_env_rejects_duplicate_normalized_keys(test_client, standard_user):
    response = await test_client.put(
        AGENT_ENV_PATH,
        json={"env": {"YUXI_TOKEN": "first", " YUXI_TOKEN ": "second"}},
        headers=standard_user["headers"],
    )
    assert response.status_code == 400


async def test_agent_env_is_user_scoped(test_client, standard_user, admin_headers):
    standard_headers = standard_user["headers"]
    user_payload = {"env": {"YUXI_USER_ONLY": "user-value"}}

    user_save_response = await test_client.put(AGENT_ENV_PATH, json=user_payload, headers=standard_headers)
    assert user_save_response.status_code == 200, user_save_response.text

    admin_response = await test_client.get(AGENT_ENV_PATH, headers=admin_headers)
    assert admin_response.status_code == 200, admin_response.text
    assert admin_response.json()["env"] != user_payload["env"]

    user_response = await test_client.get(AGENT_ENV_PATH, headers=standard_headers)
    assert user_response.status_code == 200, user_response.text
    assert user_response.json()["env"] == user_payload["env"]


USER_CONFIG_PATH = "/api/user/config"


async def test_user_config_requires_auth(test_client):
    response = await test_client.get(USER_CONFIG_PATH)
    assert response.status_code == 401


async def test_user_config_round_trip(test_client, standard_user):
    headers = standard_user["headers"]

    initial_response = await test_client.get(USER_CONFIG_PATH, headers=headers)
    assert initial_response.status_code == 200, initial_response.text
    initial_payload = initial_response.json()
    assert initial_payload["enable_memory"] is True

    save_response = await test_client.put(USER_CONFIG_PATH, json={"enable_memory": False}, headers=headers)
    assert save_response.status_code == 200, save_response.text
    assert save_response.json()["enable_memory"] is False

    final_response = await test_client.get(USER_CONFIG_PATH, headers=headers)
    assert final_response.status_code == 200, final_response.text
    assert final_response.json()["enable_memory"] is False
