"""在仓库外生成独立 Keycloak 联调环境及私有凭据。"""

import argparse
import os
import secrets
import shutil
from pathlib import Path
from urllib.parse import urlsplit


def prepare(destination: Path, yuxi_url: str) -> None:
    """只创建新目录，保留已有实验的数据和凭据。"""
    source = Path(__file__).resolve().parent
    destination = destination.expanduser().resolve()
    if destination.is_relative_to(source.parents[1]):
        raise ValueError("运行目录必须位于仓库外")
    parsed = urlsplit(yuxi_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or any(c in yuxi_url for c in "\r\n$#'\" ")
    ):
        raise ValueError("Yuxi URL 必须是无路径和凭据的完整 HTTP(S) 地址")

    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    seed = destination / "seed"
    # 容器 UID 1000 需要读取占位模板；宿主运行目录保持 0700。
    seed.mkdir(mode=0o755)
    seed.chmod(0o755)
    shutil.copyfile(source / "compose.yml", destination / "compose.yml")
    realm = seed / "yuxi-enterprise-realm.json"
    shutil.copyfile(source / realm.name, realm)
    realm.chmod(0o644)

    credentials = {
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "KC_BOOTSTRAP_ADMIN_USERNAME": "lab-admin",
        "KC_BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(32),
        "SSO_URL": "http://auth.yuxi.test:39090",
        "YUXI_REDIRECT_URI": yuxi_url.rstrip("/") + "/api/auth/oidc/callback",
        "YUXI_CLIENT_SECRET": secrets.token_urlsafe(32),
        "YUXI_LOGOUT_REDIRECT_URI": yuxi_url.rstrip("/") + "/login",
        "EMPLOYEE_DEV_PASSWORD": secrets.token_urlsafe(24),
        "EMPLOYEE_PRODUCT_PASSWORD": secrets.token_urlsafe(24),
    }
    write_env(destination / ".env", credentials)
    private = destination / ".private"
    private.mkdir(mode=0o700)
    write_env(
        private / "yuxi-oidc.env",
        {
            "OIDC_ENABLED": "true",
            "OIDC_PROVIDER_NAME": "示例企业统一登录",
            "OIDC_ISSUER_URL": credentials["SSO_URL"] + "/realms/yuxi-enterprise",
            "OIDC_CLIENT_ID": "yuxi-dev",
            "OIDC_CLIENT_SECRET": credentials["YUXI_CLIENT_SECRET"],
            "OIDC_REDIRECT_URI": credentials["YUXI_REDIRECT_URI"],
            "OIDC_AUTHORIZATION_ENDPOINT": "",
            "OIDC_TOKEN_ENDPOINT": "",
            "OIDC_USERINFO_ENDPOINT": "",
            "OIDC_END_SESSION_ENDPOINT": "",
            "OIDC_AUTO_CREATE_USER": "true",
            "OIDC_DEFAULT_ROLE": "user",
            "OIDC_USE_RAW_USERNAME": "false",
            "OIDC_FETCH_DEPARTMENT_INFO": "true",
            "OIDC_DEPARTMENT_CLAIM": "department",
            "OIDC_FORCE_PROMPT_LOGIN": "false",
        },
    )
    print(f"已生成独立运行目录：{destination}；凭据仅保存在其中的私有文件。")


def write_env(path: Path, values: dict[str, str]) -> None:
    """创建仅当前用户可读写的环境文件，不回显值。"""
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as file:
        file.write("".join(f"{key}={value}\n" for key, value in values.items()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--yuxi-url", default="http://localhost:25175")
    args = parser.parse_args()
    prepare(args.destination, args.yuxi_url)
