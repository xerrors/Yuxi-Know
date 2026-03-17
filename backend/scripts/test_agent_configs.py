import os
import sys
import time
from dataclasses import dataclass

import requests


@dataclass
class Account:
    username: str
    password: str
    label: str


ACCOUNTS = {
    "superadmin": Account("zwj", "zwj12138", "superadmin"),
    "dept_admin": Account("ceshizhuguan", "test_admin123", "dept_admin"),
    "dept_user": Account("food2025", "jnufood", "dept_user"),
}


def _base_url() -> str:
    return os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")


def _request(method: str, path: str, *, token: str | None = None, json_data=None):
    url = f"{_base_url()}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.request(method, url, headers=headers, json=json_data, timeout=60)
    return resp


def login(account: Account) -> str:
    url = f"{_base_url()}/api/auth/token"
    resp = requests.post(
        url,
        data={"username": account.username, "password": account.password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"login failed {account.label}: {resp.status_code} {resp.text}")
    data = resp.json()
    return data["access_token"], data.get("department_id"), data.get("user_id")


def get_first_agent_id(token: str) -> str:
    resp = _request("GET", "/api/chat/agent", token=token)
    if resp.status_code != 200:
        raise RuntimeError(f"get agents failed: {resp.status_code} {resp.text}")
    agents = resp.json().get("agents", [])
    if not agents:
        raise RuntimeError("no agents returned")
    return agents[0]["id"]


def list_configs(token: str, agent_id: str) -> list[dict]:
    resp = _request("GET", f"/api/chat/agent/{agent_id}/configs", token=token)
    if resp.status_code != 200:
        raise RuntimeError(f"list configs failed: {resp.status_code} {resp.text}")
    return resp.json().get("configs", [])


def get_config(token: str, agent_id: str, config_id: int) -> dict:
    resp = _request("GET", f"/api/chat/agent/{agent_id}/configs/{config_id}", token=token)
    if resp.status_code != 200:
        raise RuntimeError(f"get config failed: {resp.status_code} {resp.text}")
    return resp.json()["config"]


def create_config(token: str, agent_id: str, name: str, set_default: bool = False) -> dict:
    payload = {
        "name": name,
        "description": f"created-by-test {int(time.time())}",
        "icon": None,
        "pics": [],
        "examples": ["hello"],
        "config_json": {"context": {"system_prompt": f"system_prompt::{name}"}},
        "set_default": set_default,
    }
    resp = _request("POST", f"/api/chat/agent/{agent_id}/configs", token=token, json_data=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"create config failed: {resp.status_code} {resp.text}")
    return resp.json()["config"]


def update_config(token: str, agent_id: str, config_id: int, context_updates: dict) -> dict:
    payload = {"config_json": {"context": context_updates}}
    resp = _request("PUT", f"/api/chat/agent/{agent_id}/configs/{config_id}", token=token, json_data=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"update config failed: {resp.status_code} {resp.text}")
    return resp.json()["config"]


def set_default(token: str, agent_id: str, config_id: int) -> dict:
    resp = _request("POST", f"/api/chat/agent/{agent_id}/configs/{config_id}/set_default", token=token, json_data={})
    if resp.status_code != 200:
        raise RuntimeError(f"set default failed: {resp.status_code} {resp.text}")
    return resp.json()["config"]


def delete_config(token: str, agent_id: str, config_id: int) -> None:
    resp = _request("DELETE", f"/api/chat/agent/{agent_id}/configs/{config_id}", token=token)
    if resp.status_code != 200:
        raise RuntimeError(f"delete config failed: {resp.status_code} {resp.text}")


def chat_smoke(token: str, agent_id: str, config_id: int) -> None:
    url = f"{_base_url()}/api/chat/agent/{agent_id}"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": "ping", "config": {"thread_id": None, "agent_config_id": config_id}},
        stream=True,
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"chat failed: {resp.status_code} {resp.text}")
    lines = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        lines.append(line)
        if '"status": "finished"' in line:
            break
    if not any('"status": "init"' in s for s in lines):
        raise RuntimeError("chat stream missing init chunk")
    if not any('"status": "finished"' in s for s in lines):
        raise RuntimeError("chat stream missing finished chunk")


def assert_forbidden(resp: requests.Response, label: str):
    if resp.status_code != 403:
        raise RuntimeError(f"expected 403 for {label}, got {resp.status_code}: {resp.text}")


def main():
    super_token, super_dept_id, super_user_id = login(ACCOUNTS["superadmin"])
    test_admin_token, test_admin_dept_id, _ = login(ACCOUNTS["dept_admin"])
    default_dept_token, default_dept_id, _ = login(ACCOUNTS["dept_user"])

    agent_id = get_first_agent_id(default_dept_token)
    print("agent_id", agent_id)

    def run_dept_flow(token: str, dept_label: str):
        cfgs = list_configs(token, agent_id)
        if not cfgs:
            raise RuntimeError(f"{dept_label}: configs should have default created")
        default_cfg = next((c for c in cfgs if c.get("is_default")), cfgs[0])
        print(dept_label, "default_config", default_cfg["id"], default_cfg["name"])

        created = create_config(token, agent_id, f"{dept_label}-测试配置A", set_default=False)
        print(dept_label, "created_config", created["id"], created["name"])

        dup = create_config(token, agent_id, f"{dept_label}-测试配置A", set_default=False)
        print(dept_label, "created_duplicate_config", dup["id"], dup["name"])
        if dup["name"] == f"{dept_label}-测试配置A":
            raise RuntimeError(f"{dept_label}: duplicate name should be auto-renamed with -副本")

        updated_default = set_default(token, agent_id, created["id"])
        if not updated_default.get("is_default"):
            raise RuntimeError(f"{dept_label}: set_default should mark config as default")

        cfgs2 = list_configs(token, agent_id)
        defaults = [c for c in cfgs2 if c.get("is_default")]
        if len(defaults) != 1:
            raise RuntimeError(f"{dept_label}: default must be unique, got {len(defaults)}")

        cfg_payload = get_config(token, agent_id, created["id"])
        if cfg_payload["id"] != created["id"]:
            raise RuntimeError(f"{dept_label}: get config mismatch")

        updated = update_config(
            token,
            agent_id,
            created["id"],
            {
                "system_prompt": f"system_prompt::{dept_label}::updated",
                "tools": [],
                "knowledges": [],
                "mcps": [],
            },
        )
        if (updated.get("config_json") or {}).get("context", {}).get(
            "system_prompt"
        ) != f"system_prompt::{dept_label}::updated":
            raise RuntimeError(f"{dept_label}: update did not persist system_prompt")

        chat_smoke(token, agent_id, created["id"])

        delete_config(token, agent_id, created["id"])
        delete_config(token, agent_id, dup["id"])

        cfgs3 = list_configs(token, agent_id)
        if not cfgs3:
            raise RuntimeError(f"{dept_label}: configs should not be empty after delete; default should exist")

    run_dept_flow(default_dept_token, "default_dept")
    run_dept_flow(test_admin_token, "test_dept")

    if super_dept_id is None or super_user_id is None:
        raise RuntimeError("superadmin token missing department_id/user_id")

    tmp_user_payload = {
        "username": f"tmp_user_{int(time.time())}",
        "password": "tmp_pass_123",
        "role": "user",
        "department_id": int(super_dept_id),
    }
    created_user = _request("POST", "/api/auth/users", token=super_token, json_data=tmp_user_payload)
    if created_user.status_code != 200:
        raise RuntimeError(f"create tmp user failed: {created_user.status_code} {created_user.text}")
    tmp_user = created_user.json()
    tmp_user_login = tmp_user["user_id"]
    tmp_user_id = tmp_user["id"]

    tmp_token, _, _ = login(Account(tmp_user_login, "tmp_pass_123", "tmp_user"))
    forbidden = _request("POST", f"/api/chat/agent/{agent_id}/configs", token=tmp_token, json_data={"name": "x"})
    assert_forbidden(forbidden, "user create config")

    deleted_user = _request("DELETE", f"/api/auth/users/{tmp_user_id}", token=super_token)
    if deleted_user.status_code != 200:
        raise RuntimeError(f"delete tmp user failed: {deleted_user.status_code} {deleted_user.text}")

    print("OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e)
        sys.exit(1)
