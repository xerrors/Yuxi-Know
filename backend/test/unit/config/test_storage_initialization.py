from copy import deepcopy

import pytest
from test.unit.config._shared import load_compose


def storage_dependency_violations(compose):
    """报告绕过统一目录准备的业务进程。"""
    return {
        name
        for name in ("api", "worker", "milvus", "app-init")
        if compose["services"][name].get("depends_on", {}).get("storage-init", {}).get("condition") != "service_completed_successfully"
    }


@pytest.mark.parametrize("filename", ["docker-compose.yml", "docker-compose.prod.yml"])
def test_storage_initializer_prepares_only_consumer_mounts(filename):
    """唯一初始化器仅接管五个消费目录且不获得平台凭据。"""
    services = load_compose(filename)["services"]
    assert "milvus-storage-init" not in services
    initializer = services["storage-init"]
    assert initializer["network_mode"] == "none"
    assert initializer["user"] == "0:0"
    assert initializer["restart"] == "no"
    assert not initializer.get("environment") and not initializer.get("env_file")
    assert initializer["image"].startswith("${COMPOSE_PROJECT_NAME:-yuxi}-storage-init:")
    expected = {}
    for consumer in ("api", "milvus"):
        for volume in services[consumer]["volumes"]:
            if isinstance(volume, dict):
                source, target = volume["source"], volume["target"]
            else:
                source, target = volume.rsplit(":", 1)
            if target in ("/app/user-data", "/app/skill-sources", "/app/skill-projections", "/var/lib/milvus", "/var/lib/milvus/logs"):
                expected[target] = source
    actual = {volume.rsplit(":", 1)[1]: volume.rsplit(":", 1)[0] for volume in initializer["volumes"]}
    assert len(actual) == 5
    assert actual == expected
    assert storage_dependency_violations(load_compose(filename)) == set()


@pytest.mark.parametrize("consumer", ["api", "worker", "milvus", "app-init"])
def test_storage_gate_rejects_missing_or_nonblocking_dependency(consumer):
    """删除依赖或仅等待初始化器启动，都不能通过就绪门槛。"""
    for dependency in ({}, {"condition": "service_started"}):
        compose = deepcopy(load_compose())
        compose["services"][consumer]["depends_on"]["storage-init"] = dependency
        assert consumer in storage_dependency_violations(compose)
