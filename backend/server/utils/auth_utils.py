import hashlib
import hmac
import os
from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

from yuxi.utils.datetime_utils import utc_now

# JWT配置
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "yuxi_know_secure_key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 7 * 24 * 60 * 60  # 7天过期
PASSWORD_HASHER = PasswordHasher()


class AuthUtils:
    """认证工具类"""

    @staticmethod
    def hash_password(password: str) -> str:
        """使用 Argon2 哈希密码"""
        return PASSWORD_HASHER.hash(password)

    @staticmethod
    def verify_password(stored_password: str, provided_password: str) -> bool:
        """验证密码"""
        if stored_password.startswith("$argon2"):
            try:
                return PASSWORD_HASHER.verify(stored_password, provided_password)
            except (InvalidHash, VerifyMismatchError, VerificationError):
                return False

        # 兼容历史 SHA-256:盐 格式，避免现有账号密码在升级后立即失效。
        if ":" not in stored_password:
            return False

        hashed, salt = stored_password.split(":", 1)
        check_hash = hashlib.sha256((provided_password + salt).encode()).hexdigest()
        return hmac.compare_digest(hashed, check_hash)

    @staticmethod
    def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        """创建JWT访问令牌"""
        to_encode = data.copy()

        # 设置过期时间
        if expires_delta:
            expire = utc_now() + expires_delta
        else:
            expire = utc_now() + timedelta(seconds=JWT_EXPIRATION)

        to_encode.update({"exp": expire})

        # 编码JWT
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt

    @staticmethod
    def decode_token(token: str) -> dict[str, Any] | None:
        """解码验证JWT令牌"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.PyJWTError:
            return None

    @staticmethod
    def verify_access_token(token: str) -> dict[str, Any]:
        """验证访问令牌，如果无效则抛出异常"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("令牌已过期")
        except jwt.InvalidTokenError:
            raise ValueError("无效的令牌")
