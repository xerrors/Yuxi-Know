import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class BumpVersionScriptTests(unittest.TestCase):
    """验证版本脚本同步活动引用且保留历史记录。"""

    def _create_fixture(self, root: Path) -> Path:
        """创建包含重复版本入口和历史记录的最小仓库。"""
        script = root / "scripts/bump-version.sh"
        script.parent.mkdir(parents=True)
        shutil.copy2(Path(__file__).with_name("bump-version.sh"), script)

        fixtures = {
            "backend/pyproject.toml": 'version = "0.7.2.beta1"\n',
            "backend/uv.lock": ('name = "yuxi"\nversion = "0.7.2b1"\n'),
            "frontend/package.json": '{\n  "version": "0.7.2.beta1"\n}\n',
            "backend/test/e2e/web-tools.compose.yml": "image: ${COMPOSE_PROJECT_NAME:-yuxi}-api:${YUXI_VERSION:-0.7.2.beta1}\n",
            "docker-compose.yml": "\n".join(
                f"image: ${{COMPOSE_PROJECT_NAME:-yuxi}}-{name}:${{YUXI_VERSION:-0.7.2.beta1}}"
                for name in (
                    "api",
                    "api",
                    "api",
                    "frontend",
                )
            )
            + "\n",
            "docker-compose.prod.yml": "\n".join(
                f"image: ${{COMPOSE_PROJECT_NAME:-yuxi}}-{name}:${{YUXI_VERSION:-0.7.2.beta1}}"
                for name in ("api", "api", "api", "frontend")
            )
            + "\n",
            "README.md": (
                "当前仓库默认配置对应 `v0.7.2.beta1`。\n"
                "当前候选源码版本为 `v0.7.2.beta1`。\n"
                "git clone --branch v0.7.2.beta1 --depth 1 https://github.com/xerrors/Yuxi.git\n"
            ),
            "README.en.md": (
                "The candidate source version is `v0.7.2.beta1`.\n"
                "git clone --branch v0.7.2.beta1 --depth 1 https://github.com/xerrors/Yuxi.git\n"
            ),
            "docs/intro/quick-start.md": (
                "仓库当前默认配置对应 `v0.7.2.beta1`。\n"
                "当前候选源码版本为 `v0.7.2.beta1`。\n"
                "git clone --branch v0.7.2.beta1 --depth 1 https://github.com/xerrors/Yuxi.git\n"
            ),
            "docs/advanced/deployment.md": (
                "从 v0.7.1 升级到当前 `v0.7.2.beta1`。\n当前候选为 `0.7.2.beta1`。\ngit checkout v0.7.2.beta1\n"
            ),
            "docs/.vitepress/theme/components/YuxiHome.vue": (
                "获取 0.7.2.beta1 候选源码\ngit clone --branch v0.7.2.beta1 --depth 1 https://github.com/xerrors/Yuxi.git\n"
            ),
            "docs/develop-guides/releases/0.7.2.md": "当前候选版本为 `0.7.2.beta1`。\n",
            "docs/develop-guides/changelog.md": "当前候选为 `0.7.2.beta1`。\n\n## v0.7.2.beta1 (历史记录)\n",
        }
        for relative_path, content in fixtures.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return script

    def test_release_bump_updates_current_references_only(self) -> None:
        """正式版本升级应覆盖重复入口但不改 changelog。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = self._create_fixture(root)
            subprocess.run(
                ["bash", str(script), "0.7.2.beta2"],
                input="y\n",
                text=True,
                check=True,
                capture_output=True,
            )

            current_paths = [
                "backend/pyproject.toml",
                "frontend/package.json",
                "backend/test/e2e/web-tools.compose.yml",
                "docker-compose.yml",
                "docker-compose.prod.yml",
                "README.md",
                "README.en.md",
                "docs/intro/quick-start.md",
                "docs/advanced/deployment.md",
                "docs/.vitepress/theme/components/YuxiHome.vue",
                "docs/develop-guides/releases/0.7.2.md",
            ]
            for relative_path in current_paths:
                content = (root / relative_path).read_text()
                self.assertIn("0.7.2.beta2", content, relative_path)
                self.assertNotIn("0.7.2.beta1", content, relative_path)
                self.assertNotIn("0.7.2b1", content, relative_path)

            self.assertEqual((root / "docker-compose.yml").read_text().count("0.7.2.beta2"), 4)
            self.assertEqual((root / "docker-compose.prod.yml").read_text().count("0.7.2.beta2"), 4)
            changelog = (root / "docs/develop-guides/changelog.md").read_text()
            self.assertIn('version = "0.7.2b2"', (root / "backend/uv.lock").read_text())
            self.assertIn("v0.7.2.beta1", changelog)
            self.assertIn("当前候选为 `0.7.2.beta2`", changelog)
            self.assertNotIn("## v0.7.2.beta2", changelog)

    def test_dev_bump_keeps_release_document_references(self) -> None:
        """开发版本升级不得移动公开发布文档的稳定目标。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = self._create_fixture(root)
            subprocess.run(
                ["bash", str(script), "--dev", "0.7.2.dev2"],
                input="y\n",
                text=True,
                check=True,
                capture_output=True,
            )

            self.assertIn(
                'version = "0.7.2.dev2"',
                (root / "backend/pyproject.toml").read_text(),
            )
            for relative_path in (
                "README.md",
                "README.en.md",
                "docs/intro/quick-start.md",
                "docs/advanced/deployment.md",
                "docs/.vitepress/theme/components/YuxiHome.vue",
                "docs/develop-guides/releases/0.7.2.md",
                "docs/develop-guides/changelog.md",
            ):
                self.assertIn("0.7.2.beta1", (root / relative_path).read_text())
                self.assertNotIn("0.7.2.dev2", (root / relative_path).read_text())

    def test_invalid_version_is_rejected_before_writes(self) -> None:
        """非法版本输入必须在读取或改写项目文件前失败。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "scripts/bump-version.sh"
            script.parent.mkdir(parents=True)
            shutil.copy2(Path(__file__).with_name("bump-version.sh"), script)

            result = subprocess.run(
                ["bash", str(script), "0.7.2;touch-pwned"],
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("版本号格式无效", result.stdout)
            self.assertFalse((root / "touch-pwned").exists())


if __name__ == "__main__":
    unittest.main()
