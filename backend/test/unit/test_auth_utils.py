from __future__ import annotations

import hashlib

from server.utils.auth_utils import AuthUtils


def test_hash_password_uses_argon2():
    hashed = AuthUtils.hash_password("secret-password")

    assert hashed.startswith("$argon2")
    assert AuthUtils.verify_password(hashed, "secret-password") is True
    assert AuthUtils.verify_password(hashed, "wrong-password") is False


def test_verify_password_accepts_legacy_sha256_format():
    legacy_hash = hashlib.sha256(b"secret-passwordsalt").hexdigest()

    assert AuthUtils.verify_password(f"{legacy_hash}:salt", "secret-password") is True
    assert AuthUtils.verify_password(f"{legacy_hash}:salt", "wrong-password") is False
