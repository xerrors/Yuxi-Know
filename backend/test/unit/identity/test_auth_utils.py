from __future__ import annotations

import hashlib
import os
from datetime import timedelta

import jwt
import pytest
from yuxi.shared.datetime import utc_now

from yuxi.modules.identity.security import JWT_ALGORITHM, JWT_AUDIENCE, AuthUtils

JWT_ISSUER_PREFIX = "yuxi-know:"


def test_generate_api_key_returns_secret_hash_and_prefix():
    full_key, key_hash, key_prefix = AuthUtils.generate_api_key()

    assert full_key.startswith("yxkey_")
    assert len(full_key) == len("yxkey_") + 48
    assert key_prefix == full_key[:12]
    assert key_hash == hashlib.sha256(full_key.encode()).hexdigest()


def test_derived_api_key_is_replayable_and_independent_from_jwt_secret(monkeypatch):
    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "api-key-master-secret-one-at-least-32")
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-secret-one-at-least-thirty-two")
    first = AuthUtils.derive_api_key("request:123", 7)

    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-secret-two-at-least-thirty-two")
    replay = AuthUtils.derive_api_key("request:123", 7)
    assert replay == first

    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "api-key-master-secret-two-at-least-32")
    assert AuthUtils.derive_api_key("request:123", 7) != first


def test_api_key_derivation_secret_is_required_and_strong(monkeypatch):
    monkeypatch.delenv("API_KEY_DERIVATION_SECRET", raising=False)
    with pytest.raises(ValueError, match="API_KEY_DERIVATION_SECRET"):
        AuthUtils.require_api_key_derivation_secret()

    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "too-short")
    with pytest.raises(ValueError, match="至少 32"):
        AuthUtils.derive_api_key("request:123", 7)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("JWT_SECRET_KEY", "x" * 30, "至少 32"),
        ("JWT_SECRET_KEY", " jwt-secret-that-is-long-enough ", "首尾空白"),
        ("API_KEY_DERIVATION_SECRET", "x" * 30, "至少 32"),
        ("SANDBOX_PROVISIONER_TOKEN", "x" * 30, "至少 32"),
    ],
)
def test_runtime_rejects_invalid_effective_security_secret(monkeypatch, name, value, message):
    """dotenv 去引号后的进程值仍必须在最终信任边界重新校验。"""

    monkeypatch.setenv("YUXI_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-secret-that-is-distinct-and-at-least-32")
    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "api-key-secret-that-is-distinct-and-at-least-32")
    monkeypatch.setenv("SANDBOX_PROVISIONER_TOKEN", "sandbox-secret-that-is-distinct-and-at-least-32")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        AuthUtils.require_security_secrets()


@pytest.mark.parametrize(
    ("first_name", "second_name"),
    [
        ("JWT_SECRET_KEY", "API_KEY_DERIVATION_SECRET"),
        ("API_KEY_DERIVATION_SECRET", "SANDBOX_PROVISIONER_TOKEN"),
        ("JWT_SECRET_KEY", "SANDBOX_PROVISIONER_TOKEN"),
    ],
)
def test_security_secrets_must_not_be_reused(monkeypatch, first_name, second_name):
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-secret-that-is-distinct-and-at-least-32")
    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "api-key-secret-that-is-distinct-and-at-least-32")
    monkeypatch.setenv("SANDBOX_PROVISIONER_TOKEN", "sandbox-secret-that-is-distinct-and-at-least-32")
    shared_secret = "shared-security-secret-that-is-at-least-32-chars"
    monkeypatch.setenv(first_name, shared_secret)
    monkeypatch.setenv(second_name, shared_secret)

    with pytest.raises(ValueError, match="安全密钥必须相互独立"):
        AuthUtils.require_api_key_derivation_secret()


def test_hash_password_uses_argon2():
    hashed = AuthUtils.hash_password("secret-password")

    assert hashed.startswith("$argon2")
    assert AuthUtils.verify_password(hashed, "secret-password") is True
    assert AuthUtils.verify_password(hashed, "wrong-password") is False


def test_access_token_contains_instance_claims(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-enough-randomness")
    monkeypatch.setenv("YUXI_INSTANCE_ID", "pytest-instance")

    token = AuthUtils.create_access_token({"sub": "1"})
    payload = AuthUtils.verify_access_token(token)

    assert payload["sub"] == "1"
    assert payload["iss"] == f"{JWT_ISSUER_PREFIX}pytest-instance"
    assert payload["aud"] == JWT_AUDIENCE


def test_access_token_auto_generates_dev_secret(monkeypatch):
    monkeypatch.setenv("YUXI_ENV", "development")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("YUXI_INSTANCE_ID", "pytest-instance")

    token = AuthUtils.create_access_token({"sub": "1"})

    assert AuthUtils.verify_access_token(token)["sub"] == "1"
    assert len(os.environ["JWT_SECRET_KEY"]) == 64


def test_access_token_requires_configured_secret_in_production(monkeypatch):
    monkeypatch.setenv("YUXI_ENV", "production")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("YUXI_INSTANCE_ID", "pytest-instance")

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        AuthUtils.create_access_token({"sub": "1"})


def test_access_token_rejects_public_default_secret_in_production(monkeypatch):
    monkeypatch.setenv("YUXI_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "yuxi_know_secure_key")
    monkeypatch.setenv("YUXI_INSTANCE_ID", "pytest-instance")

    with pytest.raises(ValueError, match="公开默认密钥"):
        AuthUtils.create_access_token({"sub": "1"})


def test_access_token_auto_generates_dev_instance_id(monkeypatch):
    monkeypatch.setenv("YUXI_ENV", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-enough-randomness")
    monkeypatch.delenv("YUXI_INSTANCE_ID", raising=False)

    token = AuthUtils.create_access_token({"sub": "1"})

    assert AuthUtils.verify_access_token(token)["iss"].startswith(f"{JWT_ISSUER_PREFIX}instance-")
    assert os.environ["YUXI_INSTANCE_ID"].startswith("instance-")


def test_access_token_requires_instance_id_in_production(monkeypatch):
    monkeypatch.setenv("YUXI_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-enough-randomness")
    monkeypatch.delenv("YUXI_INSTANCE_ID", raising=False)

    with pytest.raises(ValueError, match="YUXI_INSTANCE_ID"):
        AuthUtils.create_access_token({"sub": "1"})


def test_verify_access_token_rejects_wrong_issuer(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-enough-randomness")
    monkeypatch.setenv("YUXI_INSTANCE_ID", "pytest-instance")
    token = jwt.encode(
        {"sub": "1", "exp": utc_now() + timedelta(minutes=5), "iss": f"{JWT_ISSUER_PREFIX}other", "aud": JWT_AUDIENCE},
        "test-secret-key-with-enough-randomness",
        algorithm=JWT_ALGORITHM,
    )

    assert AuthUtils.decode_token(token) is None


def test_verify_access_token_rejects_wrong_audience(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-enough-randomness")
    monkeypatch.setenv("YUXI_INSTANCE_ID", "pytest-instance")
    token = jwt.encode(
        {
            "sub": "1",
            "exp": utc_now() + timedelta(minutes=5),
            "iss": f"{JWT_ISSUER_PREFIX}pytest-instance",
            "aud": "other-api",
        },
        "test-secret-key-with-enough-randomness",
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(ValueError, match="无效的令牌"):
        AuthUtils.verify_access_token(token)


def test_verify_access_token_requires_claims(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-enough-randomness")
    monkeypatch.setenv("YUXI_INSTANCE_ID", "pytest-instance")
    token = jwt.encode(
        {"sub": "1", "exp": utc_now() + timedelta(minutes=5)},
        "test-secret-key-with-enough-randomness",
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(ValueError, match="无效的令牌"):
        AuthUtils.verify_access_token(token)
