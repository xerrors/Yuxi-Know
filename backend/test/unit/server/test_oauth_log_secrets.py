"""异常堆栈保留定位信息，但不展开 OAuth 等局部凭据。"""

from yuxi.infrastructure.observability import logging as logs


def fail_with_private_payload(payload):
    """故意让失败行引用包含私有令牌的本地变量。"""
    return payload["missing-field"]


def test_exception_logging_does_not_expand_private_locals(monkeypatch, tmp_path):
    """恢复 diagnose 默认值后，该日志会包含 payload 中的私有令牌。"""
    target = tmp_path / "oauth.log"
    try:
        with monkeypatch.context() as patch:
            patch.setattr(logs, "LOG_DIR", tmp_path)
            patch.setattr(logs, "LOG_FILE", str(target))
            logger = logs.setup_logger("oauth-fixture", console=False)
            marker = "fixture-private-refresh-token"
            try:
                fail_with_private_payload({"refresh_token": marker})
            except KeyError:
                logger.exception("OAuth fixture failed")
            logger.complete()
            content = target.read_text()
            assert "KeyError" in content and "fail_with_private_payload" in content
            assert marker not in content
    finally:
        logs.setup_logger("Yuxi")
