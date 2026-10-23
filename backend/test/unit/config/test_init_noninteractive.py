import os
from pathlib import Path
import subprocess

import pytest

from test.unit.config._shared import project_root


def isolated_environment():
    """子进程只继承工具定位信息，避免应用导入的真实凭据污染合成用例。"""
    return {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"}
    }


def run_init(tmp_path: Path, **overrides):
    """以关闭标准输入的真实 shell 入口初始化隔离环境。"""
    env = isolated_environment()
    env.update(YUXI_ENV_FILE=".env.prod", YUXI_INIT_NON_INTERACTIVE="1", YUXI_INIT_SKIP_IMAGES="1")
    env.update(overrides)
    return subprocess.run(
        ["bash", str(project_root() / "scripts/init.sh")],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
    )


def read_env(tmp_path: Path):
    """回读初始化实际写入的变量。"""
    return dict(
        line.split("=", 1) for line in (tmp_path / ".env.prod").read_text().splitlines() if "=" in line and not line.startswith("#")
    )


def test_env_overrides_create_selected_file_and_preserve_secrets_on_rerun(tmp_path):
    """环境输入写入独立文件，重复初始化保留持久密钥。"""
    result = run_init(
        tmp_path,
        SILICONFLOW_API_KEY="test-api-key",
        YUXI_INSTANCE_ID="Production",
        WEB_SEARCH_PROVIDER="tavily",
        TAVILY_API_KEY="test-search-key",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    values = read_env(tmp_path)
    assert values["SILICONFLOW_API_KEY"] == "test-api-key"
    assert values["YUXI_INSTANCE_ID"] == "Production"
    assert values["TAVILY_API_KEY"] == "test-search-key"
    assert len(values["JWT_SECRET_KEY"]) >= 32
    assert values["JWT_SECRET_KEY"] != values["API_KEY_DERIVATION_SECRET"]
    assert not (tmp_path / ".env").exists()
    assert (tmp_path / ".env.prod").stat().st_mode & 0o777 == 0o600
    assert "test-api-key" not in result.stdout + result.stderr
    result = run_init(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert read_env(tmp_path) == values


def test_missing_api_key_fails_without_prompt(tmp_path):
    """无人值守缺少必填项时返回明确错误。"""
    result = run_init(tmp_path, SILICONFLOW_API_KEY="")
    assert result.returncode != 0
    assert "SILICONFLOW_API_KEY" in result.stderr


@pytest.mark.parametrize("secret", ["short", " padded-secret-value-that-is-at-least-32-characters "])
def test_invalid_explicit_secret_is_rejected(tmp_path, secret):
    """显式非法密钥不能被生成值掩盖。"""
    result = run_init(tmp_path, SILICONFLOW_API_KEY="test-key", JWT_SECRET_KEY=secret)
    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr
    assert secret not in result.stderr


def test_reused_secrets_are_rejected(tmp_path):
    """两个应用安全密钥必须独立。"""
    secret = "s" * 64
    result = run_init(tmp_path, SILICONFLOW_API_KEY="test-key", JWT_SECRET_KEY=secret, API_KEY_DERIVATION_SECRET=secret)
    assert result.returncode != 0
    assert "API_KEY_DERIVATION_SECRET" in result.stderr


def test_invalid_existing_secret_is_not_rotated(tmp_path):
    """已有非空非法密钥导致失败且保留原值。"""
    (tmp_path / ".env.prod").write_text("SILICONFLOW_API_KEY=test-key\nJWT_SECRET_KEY=short\n")
    result = run_init(tmp_path)
    assert result.returncode != 0
    assert read_env(tmp_path)["JWT_SECRET_KEY"] == "short"


def test_production_generates_credentials_and_requires_cube_address(tmp_path):
    """生产初始化生成服务凭据并要求执行节点地址。"""
    result = run_init(tmp_path, YUXI_ENV="production", SILICONFLOW_API_KEY="test-key")
    assert result.returncode != 0
    assert "CUBE_API_URL" in result.stderr
    result = run_init(
        tmp_path,
        YUXI_ENV="production",
        CUBE_API_URL="http://node:3000",
        CUBE_PROXY_NODE_IP="node",
        CUBE_NODE_USER_DATA_DIR="/data/shared/production/threads",
        CUBE_NODE_SKILL_PROJECTION_DIR="/data/shared/production/skills",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    values = read_env(tmp_path)
    for name in ["POSTGRES_PASSWORD", "NEO4J_PASSWORD", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"]:
        assert len(values[name]) >= 32
    assert values["YUXI_ENV"] == "production"


@pytest.mark.parametrize("filename", ["docker-compose.yml", "docker-compose.prod.yml"])
@pytest.mark.parametrize("paths", [None, "", "/data/shared/custom"])
def test_cube_compose_defaults_and_explicit_paths_after_init(tmp_path, filename, paths):
    """真实初始化和 Compose 解析保留默认目录或部署者指定的映射。"""
    import json
    import shutil

    if not shutil.which("docker"):
        pytest.skip("需要 Docker Compose 命令验证部署配置")
    overrides = {}
    if paths is not None:
        overrides = {
            "CUBE_NODE_USER_DATA_DIR": f"{paths}/threads" if paths else "",
            "CUBE_NODE_SKILL_PROJECTION_DIR": f"{paths}/skills" if paths else "",
        }
    result = run_init(
        tmp_path,
        YUXI_ENV="production" if ".prod." in filename else "development",
        SILICONFLOW_API_KEY="test-key",
        CUBE_API_URL="http://node:3000",
        CUBE_PROXY_NODE_IP="node",
        **overrides,
    )
    assert result.returncode == 0, result.stderr
    env_file = tmp_path / ".env.prod"
    rendered = subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "-f", str(project_root() / filename), "config", "--format", "json"],
        env={**isolated_environment(), "YUXI_ENV_FILE": str(env_file)},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert rendered.returncode == 0, rendered.stderr
    services = json.loads(rendered.stdout)["services"]
    for name in ("api", "worker", "app-init"):
        env = services[name]["environment"]
        assert env["CUBE_NODE_USER_DATA_DIR"] == (f"{paths}/threads" if paths else "/data/shared/yuxi/threads")
        assert env["CUBE_NODE_SKILL_PROJECTION_DIR"] == (f"{paths}/skills" if paths else "/data/shared/yuxi/skill-projections")
        assert env["CUBE_PROXY_PORT_HTTP"] == "80"
        assert env["CUBE_TEMPLATE_ID"] == "yuxi-user"


def test_container_backend_generates_runner_token_in_development(tmp_path):
    """开发 container 模式也自动生成 runner token，避免首次启动健康检查失败。"""
    result = run_init(tmp_path, SANDBOX_BACKEND="container", SILICONFLOW_API_KEY="test-key")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(read_env(tmp_path)["SANDBOX_RUNNER_TOKEN"]) >= 32


def test_production_container_backend_requires_runner_credentials(tmp_path):
    """生产 container 模式要求镜像 digest，并自动生成 runner token。"""
    result = run_init(tmp_path, YUXI_ENV="production", SANDBOX_BACKEND="container", SILICONFLOW_API_KEY="test-key")
    assert result.returncode != 0
    assert "SANDBOX_CONTAINER_IMAGE" in result.stderr
    result = run_init(
        tmp_path,
        YUXI_ENV="production",
        SANDBOX_BACKEND="container",
        SILICONFLOW_API_KEY="test-key",
        SANDBOX_CONTAINER_IMAGE="registry.example/yuxi-sandbox:0.8.0",
        SANDBOX_CONTAINER_IMAGE_DIGEST="sha256:" + "a" * 64,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    values = read_env(tmp_path)
    assert len(values["SANDBOX_RUNNER_TOKEN"]) >= 32
    assert values["SANDBOX_CONTAINER_IMAGE_DIGEST"].startswith("sha256:")


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"SILICONFLOW_API_KEY": "key\nINJECTED=value"}, "single-line"),
        ({"WEB_SEARCH_PROVIDER": "unknown"}, "WEB_SEARCH_PROVIDER"),
        ({"YUXI_INIT_NON_INTERACTIVE": "yes"}, "must be 0 or 1"),
    ],
)
def test_invalid_configuration_fails_without_leaking_values(tmp_path, overrides, error):
    """边界拒绝配置注入、未知供应商与非法开关。"""
    result = run_init(tmp_path, **{"SILICONFLOW_API_KEY": "test-key", **overrides})
    assert result.returncode != 0
    assert error in result.stderr
    assert "INJECTED=value" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "key",
    [
        "test-$UNSET_VARIABLE-${UNSET_VARIABLE}-#-quote'and\\slash",
        "test-$FOO\\",
        "test-\\'quote",
        "test-\\\\'quote\\",
    ],
)
def test_environment_values_roundtrip_through_compose_without_interpolation(tmp_path, key):
    """Compose 实际解析后的凭据保留美元符、引号与注释字符。"""
    import shutil

    if not shutil.which("docker"):
        pytest.skip("需要 Docker Compose 命令验证 dotenv 协议")
    result = run_init(tmp_path, SILICONFLOW_API_KEY=key)
    assert result.returncode == 0, result.stderr
    (tmp_path / "compose.yml").write_text("services:\n  probe:\n    image: busybox\n    env_file: [.env.prod]\n")
    parsed = subprocess.run(
        ["docker", "compose", "--env-file", ".env.prod", "-f", "compose.yml", "config", "--environment"],
        cwd=tmp_path,
        env=isolated_environment(),
        capture_output=True,
        text=True,
        check=True,
    )
    assert dict(line.split("=", 1) for line in parsed.stdout.splitlines() if "=" in line)["SILICONFLOW_API_KEY"] == key
    import json

    service_config = subprocess.run(
        ["docker", "compose", "--env-file", ".env.prod", "-f", "compose.yml", "config", "--format", "json"],
        cwd=tmp_path,
        env=isolated_environment(),
        capture_output=True,
        text=True,
        check=True,
    )
    # config 输出再次转义美元符，供输出内容作为 Compose 文件复用。
    injected = json.loads(service_config.stdout)["services"]["probe"]["environment"]["SILICONFLOW_API_KEY"]
    assert injected.replace("$$", "$") == key
    rerun = run_init(tmp_path)
    assert rerun.returncode == 0, rerun.stderr
    parsed = subprocess.run(
        ["docker", "compose", "--env-file", ".env.prod", "-f", "compose.yml", "config", "--environment"],
        cwd=tmp_path,
        env=isolated_environment(),
        capture_output=True,
        text=True,
        check=True,
    )
    assert dict(line.split("=", 1) for line in parsed.stdout.splitlines() if "=" in line)["SILICONFLOW_API_KEY"] == key


@pytest.mark.parametrize("quoted_key", ['"test-existing-key"', "'test-existing-key' # inline comment"])
def test_existing_quoted_key_is_preserved_on_rerun(tmp_path, quoted_key):
    """已有 dotenv 引号与行末注释不能变成凭据正文。"""
    existing = f"SILICONFLOW_API_KEY={quoted_key}\n"
    (tmp_path / ".env.prod").write_text(existing)
    result = run_init(tmp_path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".env.prod").read_text().startswith(existing)


@pytest.mark.parametrize("value,error", [("'unterminated", "unterminated quote"), ('"key"unexpected', "unexpected text")])
def test_malformed_existing_dotenv_value_fails_clearly(tmp_path, value, error):
    """已有非法引号值不被伪装成可用配置。"""
    (tmp_path / ".env.prod").write_text(f"SILICONFLOW_API_KEY={value}\n")
    result = run_init(tmp_path)
    assert result.returncode != 0
    assert error in result.stderr


def test_search_keys_are_optional_and_deepseek_environment_is_preserved(tmp_path):
    """初始化不询问搜索凭据，已有缺 Key 选择也不阻断部署。"""
    result = run_init(
        tmp_path,
        SILICONFLOW_API_KEY="test-model-key",
        WEB_SEARCH_PROVIDER="doubao",
        DOUBAO_SEARCH_API_KEY="",
        DEEPSEEK_API_KEY="test-deepseek-key",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    values = read_env(tmp_path)
    assert values["WEB_SEARCH_PROVIDER"] == "doubao"
    assert values["DEEPSEEK_API_KEY"] == "test-deepseek-key"
    assert "test-deepseek-key" not in result.stdout + result.stderr
