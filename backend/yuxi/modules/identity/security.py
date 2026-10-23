import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

from yuxi.shared.datetime import utc_now

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 7 * 24 * 60 * 60
JWT_AUDIENCE = "yuxi-know-api"
PUBLIC_DEFAULT_JWT_SECRET_KEY = "yuxi_know_secure_key"
PASSWORD_HASHER = PasswordHasher()
SECURITY_SECRET_NAMES = (
    "JWT_SECRET_KEY",
    "API_KEY_DERIVATION_SECRET",
)


def _is_production_env() -> bool:
    return os.environ.get("YUXI_ENV", "development").strip().lower() in {"prod", "production"}


def _get_or_create_dev_env(name: str, value_factory) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if _is_production_env():
        raise ValueError(f"{name} 未配置，请在生产环境的 .env.prod 中设置持久化随机值")

    value = value_factory()
    os.environ[name] = value
    print(f"{name} 未配置，开发环境已自动生成临时随机值，服务重启后会重新生成。")
    return value


def _validate_configured_security_secrets(*, required_names: tuple[str, ...]) -> dict[str, str]:
    """校验进程实际收到的安全密钥，而不是 dotenv 原始文本。"""

    values = {name: os.environ.get(name, "") for name in SECURITY_SECRET_NAMES}
    for name in required_names:
        if not values[name]:
            raise ValueError(f"{name} 未配置")
    for name, value in values.items():
        if not value:
            continue
        if value != value.strip():
            raise ValueError(f"{name} 不能包含首尾空白")
        if len(value) < 32:
            raise ValueError(f"{name} 必须配置为至少 32 个字符的持久随机值")

    populated = [(name, value) for name, value in values.items() if value]
    for index, (name, value) in enumerate(populated):
        for other_name, other_value in populated[index + 1 :]:
            if hmac.compare_digest(value, other_value):
                raise ValueError(f"安全密钥必须相互独立: {name} 与 {other_name} 不得复用")
    return values


def _get_jwt_secret_key() -> str:
    secret_key = os.environ.get("JWT_SECRET_KEY", "")
    if not secret_key:
        if _is_production_env():
            raise ValueError("JWT_SECRET_KEY 未配置，请在生产环境的 .env.prod 中设置持久化随机值")
        secret_key = secrets.token_hex(32)
        os.environ["JWT_SECRET_KEY"] = secret_key
        print("JWT_SECRET_KEY 未配置，开发环境已自动生成临时随机值，服务重启后会重新生成。")
    if _is_production_env() and secret_key == PUBLIC_DEFAULT_JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY 不能使用公开默认密钥，请重新生成随机强密钥")
    _validate_configured_security_secrets(required_names=("JWT_SECRET_KEY",))
    return secret_key


def _get_api_key_derivation_secret() -> str:
    return _validate_configured_security_secrets(required_names=("API_KEY_DERIVATION_SECRET",))["API_KEY_DERIVATION_SECRET"]


def _get_jwt_issuer() -> str:
    instance_id = _get_or_create_dev_env("YUXI_INSTANCE_ID", lambda: f"instance-{secrets.token_hex(8)}")
    return f"yuxi-know:{instance_id}"


class AuthUtils:
    @staticmethod
    def generate_api_key() -> tuple[str, str, str]:
        random_part = secrets.token_hex(24)
        full_key = f"yxkey_{random_part}"
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        key_prefix = full_key[:12]
        return full_key, key_hash, key_prefix

    @staticmethod
    def derive_api_key(idempotency_scope: str, subject_id: int | str) -> tuple[str, str, str]:
        """由稳定幂等域确定性派生可重放的 API Key，数据库仍只保存 hash。"""

        scope = str(idempotency_scope).strip()
        if not scope:
            raise ValueError("API Key 幂等域不能为空")
        payload = f"yuxi-api-key-v1:{subject_id}:{scope}".encode()
        digest = hmac.new(_get_api_key_derivation_secret().encode(), payload, hashlib.sha256).hexdigest()
        full_key = f"yxkey_{digest[:48]}"
        return full_key, hashlib.sha256(full_key.encode()).hexdigest(), full_key[:12]

    @staticmethod
    def require_api_key_derivation_secret() -> None:
        """在服务发布前验证独立、持久的 API Key 派生主密钥。"""

        _get_api_key_derivation_secret()

    @staticmethod
    def require_security_secrets() -> None:
        """在任何外部服务启动前校验三项真实运行时安全密钥。"""

        _get_jwt_secret_key()
        _validate_configured_security_secrets(required_names=SECURITY_SECRET_NAMES)

    @staticmethod
    def hash_password(password: str) -> str:
        return PASSWORD_HASHER.hash(password)

    @staticmethod
    def verify_password(stored_password: str, provided_password: str) -> bool:
        if not stored_password.startswith("$argon2"):
            return False
        try:
            return PASSWORD_HASHER.verify(stored_password, provided_password)
        except (InvalidHash, VerifyMismatchError, VerificationError):
            return False

    @staticmethod
    def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        to_encode = data.copy()
        expire = utc_now() + (expires_delta or timedelta(seconds=JWT_EXPIRATION))
        to_encode.update({"exp": expire, "iss": _get_jwt_issuer(), "aud": JWT_AUDIENCE, "jti": secrets.token_urlsafe(32)})
        return jwt.encode(to_encode, _get_jwt_secret_key(), algorithm=JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict[str, Any] | None:
        try:
            return jwt.decode(
                token,
                _get_jwt_secret_key(),
                algorithms=[JWT_ALGORITHM],
                issuer=_get_jwt_issuer(),
                audience=JWT_AUDIENCE,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except (jwt.PyJWTError, ValueError):
            return None

    @staticmethod
    def verify_access_token(token: str) -> dict[str, Any]:
        try:
            return jwt.decode(
                token,
                _get_jwt_secret_key(),
                algorithms=[JWT_ALGORITHM],
                issuer=_get_jwt_issuer(),
                audience=JWT_AUDIENCE,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError:
            raise ValueError("令牌已过期")
        except jwt.InvalidTokenError:
            raise ValueError("无效的令牌")


KNOWLEDGE_MCP_AUDIENCE = "yuxi-knowledge-mcp"
KNOWLEDGE_MCP_PURPOSE = "agent-knowledge-read"
KNOWLEDGE_DELEGATION_SECONDS = 300


def create_knowledge_token(*, uid: str, selection: str | list[str], run_id: str | None = None) -> str:
    """仅供可信运行上下文签发五分钟知识库只读委托。"""
    if not uid or not _valid_knowledge_selection(selection):
        raise ValueError("知识库委托缺少用户或有效选择范围")
    secret, issuer = require_knowledge_delegation_config()
    now = utc_now()
    return jwt.encode(
        {
            "sub": uid,
            "iss": issuer,
            "aud": KNOWLEDGE_MCP_AUDIENCE,
            "purpose": KNOWLEDGE_MCP_PURPOSE,
            "selection": selection,
            "run_id": run_id,
            "iat": now,
            "exp": now + timedelta(seconds=KNOWLEDGE_DELEGATION_SECONDS),
        },
        secret,
        algorithm=JWT_ALGORITHM,
    )


def verify_knowledge_token(token: str) -> dict[str, Any]:
    """拒绝登录 Token、其他用途和不合法委托范围。"""
    secret, issuer = require_knowledge_delegation_config()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            issuer=issuer,
            audience=KNOWLEDGE_MCP_AUDIENCE,
            options={"require": ["sub", "iss", "aud", "purpose", "selection", "iat", "exp"]},
        )
        if (
            payload["purpose"] != KNOWLEDGE_MCP_PURPOSE
            or not payload["sub"]
            or not _valid_knowledge_selection(payload["selection"])
            or not 0 < payload["exp"] - payload["iat"] <= KNOWLEDGE_DELEGATION_SECONDS
        ):
            raise ValueError("无效的知识库委托")
        return payload
    except (jwt.PyJWTError, TypeError, KeyError) as exc:
        raise ValueError("无效或过期的知识库委托") from exc


def require_knowledge_delegation_config() -> tuple[str, str]:
    """委托跨进程使用部署密钥和实例标识，禁止隐式随机配置。"""
    secret = _validate_configured_security_secrets(required_names=("JWT_SECRET_KEY",))["JWT_SECRET_KEY"]
    instance_id = os.environ.get("YUXI_INSTANCE_ID", "").strip()
    if not instance_id:
        raise ValueError("Knowledge MCP 委托需要配置共享 YUXI_INSTANCE_ID")
    return secret, f"yuxi-know:{instance_id}"


def _valid_knowledge_selection(selection: object) -> bool:
    """接受 all 或全为非空字符串的列表，显式空列表保持空范围。"""
    if selection == "all":
        return True
    return isinstance(selection, list) and all(isinstance(item, str) and item.strip() for item in selection)
