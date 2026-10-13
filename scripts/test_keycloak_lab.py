"""验证实验配置生成器保护既有凭据及容器可读的占位导入。"""

import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("keycloak_lab_prepare", ROOT / "docker/keycloak-lab/prepare.py")
prepare_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_module)


class KeycloakLabPreparationTests(unittest.TestCase):
    """从生成文件证明隔离和凭据约束。"""

    def test_private_credentials_and_readable_placeholder_seed(self):
        """密钥文件保持私有，容器读取的模板只有占位符。"""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "lab"
            prepare_module.prepare(target, "http://localhost:25175")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
            for file in [target / ".env", target / ".private/yuxi-oidc.env"]:
                self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
            seed = target / "seed/yuxi-enterprise-realm.json"
            self.assertEqual(stat.S_IMODE(seed.parent.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(seed.stat().st_mode), 0o644)
            realm = json.loads(seed.read_text())
            self.assertEqual(realm["clients"][0]["secret"], "${YUXI_CLIENT_SECRET}")
            self.assertEqual(realm["clients"][0]["redirectUris"], ["${YUXI_REDIRECT_URI}"])
            attributes = realm["clients"][0]["attributes"]
            self.assertEqual(attributes["pkce.code.challenge.method"], "S256")
            self.assertEqual(attributes["post.logout.redirect.uris"], "${YUXI_LOGOUT_REDIRECT_URI}")
            self.assertEqual(attributes["backchannel.logout.url"], "http://api:5050/api/auth/oidc/backchannel-logout")
            env = dict(line.split("=", 1) for line in (target / ".env").read_text().splitlines())
            self.assertEqual(env["YUXI_LOGOUT_REDIRECT_URI"], "http://localhost:25175/login")
            self.assertNotIn(env["YUXI_CLIENT_SECRET"], seed.read_text())
            self.assertGreater(len(env["YUXI_CLIENT_SECRET"]), 32)
            self.assertIn("OIDC_DEFAULT_ROLE=user\n", (target / ".private/yuxi-oidc.env").read_text())

    def test_existing_directory_is_not_overwritten(self):
        """重复运行不能轮换已有服务的凭据。"""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            sentinel = target / ".env"
            sentinel.write_text("existing-private-config\n")
            with self.assertRaises(FileExistsError):
                prepare_module.prepare(target, "http://localhost:25175")
            self.assertEqual(sentinel.read_text(), "existing-private-config\n")

    def test_repository_destination_is_rejected(self):
        """禁止把运行密钥写入仓库。"""
        with self.assertRaisesRegex(ValueError, "仓库外"):
            prepare_module.prepare(ROOT / "generated-lab", "http://localhost:25175")

    def test_invalid_origin_does_not_create_files(self):
        """非法回调来源或换行不能污染环境文件。"""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "lab"
            for url in ["file:///tmp", "http://user:pass@localhost", "http://localhost/path", "http://localhost\nINJECT=true"]:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    prepare_module.prepare(target, url)
                self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
