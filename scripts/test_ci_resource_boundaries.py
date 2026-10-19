"""验证临时托管探针拒绝普通机器及 self-hosted runner。"""

import os
import copy
import json
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HostedProbeTests(unittest.TestCase):
    """安装与真实 VM 探针不能误用于持久环境。"""

    def test_probe_rejects_non_hosted_environment_before_side_effects(self):
        """恢复缺失的托管边界时，负控必须失败。"""
        with tempfile.TemporaryDirectory() as root:
            self._check_rejection(Path(root))

    def _check_rejection(self, root: Path) -> None:
        """替换副作用命令，guard 回归也不能安装到本机。"""
        calls = root / "calls"
        for command in ("sudo", "curl"):
            shim = root / command
            shim.write_text(f"#!/bin/sh\nprintf '%s\\n' called >> '{calls}'\nexit 99\n")
            shim.chmod(0o755)
        for script in ("ci_probe_kvm.py", "ci_probe_cube_workspace.py", "ci_probe_hosted_cube.sh", "ci_prepare_system_tests_env.sh"):
            for github, runner in (("false", "github-hosted"), ("true", "self-hosted"), ("", "")):
                with self.subTest(script=script, github=github, runner=runner):
                    result = subprocess.run(
                        ["bash" if script.endswith(".sh") else sys.executable, str(ROOT / "scripts" / script)],
                        env={
                            **os.environ, "GITHUB_ACTIONS": github, "RUNNER_ENVIRONMENT": runner,
                            "PATH": f"{root}:{os.environ['PATH']}",
                            "CUBE_API_URL": "http://127.0.0.1:1", "CUBE_PROXY_NODE_IP": "127.0.0.1",
                        },
                        capture_output=True, text=True, timeout=5,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("仅允许在 GitHub 临时托管执行器运行", result.stderr)
                    self.assertFalse(calls.exists(), "guard 拒绝前调用了副作用命令")


class ServiceIntegrationTests(unittest.TestCase):
    """迁移后的数据库检查在托管 job 中拥有实际执行入口。"""

    def assert_service_inventory(self, workflow: str, script: str) -> None:
        """保留原工程门禁拥有的 Schema、FIFO 与 lease 选择器。"""
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("run: bash scripts/ci_run_service_integration.sh", workflow)
        command = re.search(r"(?m)^uv run --locked --group test pytest (.*)", script.replace("\\\n", ""))
        self.assertIsNotNone(command, "缺少实际 pytest 命令")
        selectors = shlex.split(command.group(1), comments=True)
        for name in ("schema_migration_version", "agent_input_concurrency", "agent_run_lease"):
            self.assertIn(f"test/integration/services/test_{name}.py", selectors)

    def test_service_inventory_is_wired(self):
        """执行入口与迁移后的关键检查共同存在。"""
        self.assert_service_inventory(
            (ROOT / ".github/workflows/service-integration.yml").read_text(),
            (ROOT / "scripts/ci_run_service_integration.sh").read_text(),
        )

    def test_service_setup_requires_explicit_resource_locations(self):
        """遗漏任一资源位置时不得初始化默认数据库或 Skill 目录。"""
        with tempfile.TemporaryDirectory() as root:
            calls = Path(root) / "calls"
            uv = Path(root) / "uv"
            uv.write_text(f"#!/bin/sh\nprintf '%s\\n' called >> '{calls}'\nexit 99\n")
            uv.chmod(0o755)
            resources = {"POSTGRES_URL": "fixture", "REDIS_URL": "fixture", "YUXI_SKILL_DATA_DIR": root}
            for missing in resources:
                with self.subTest(missing=missing):
                    result = subprocess.run(
                        ["bash", str(ROOT / "scripts/ci_run_service_integration.sh")],
                        env={"PATH": f"{root}:{os.environ['PATH']}", **{k: v for k, v in resources.items() if k != missing}},
                        capture_output=True, text=True, timeout=5,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(missing, result.stderr)
                    self.assertFalse(calls.exists(), "位置校验前执行了初始化")

    def test_service_setup_rejects_local_dotenv_before_initialization(self):
        """本地部署配置不能覆盖显式传入的测试资源。"""
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / "backend").mkdir()
            (base / "backend/.env").write_text("POSTGRES_URL=deployment-sentinel\n")
            (base / "scripts").mkdir()
            script = base / "scripts/ci_run_service_integration.sh"
            script.write_text((ROOT / "scripts/ci_run_service_integration.sh").read_text())
            calls = base / "calls"
            uv = base / "uv"
            uv.write_text(f"#!/bin/sh\nprintf '%s\\n' called >> '{calls}'\nexit 99\n")
            uv.chmod(0o755)
            result = subprocess.run(
                ["bash", str(script)],
                env={
                    "PATH": f"{root}:{os.environ['PATH']}", "POSTGRES_URL": "fixture",
                    "REDIS_URL": "fixture", "YUXI_SKILL_DATA_DIR": root,
                },
                capture_output=True, text=True, timeout=5,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("拒绝加载 backend/.env", result.stderr)
            self.assertFalse(calls.exists(), "dotenv 拒绝前执行了初始化")

    def test_service_inventory_rejects_lost_execution_or_selectors(self):
        """删除选择器、注释执行入口或恢复 self-hosted 时必须拒绝。"""
        workflow = (ROOT / ".github/workflows/service-integration.yml").read_text()
        script = (ROOT / "scripts/ci_run_service_integration.sh").read_text()
        for name in ("schema_migration_version", "agent_input_concurrency", "agent_run_lease"):
            with self.subTest(name=name), self.assertRaises(AssertionError):
                self.assert_service_inventory(workflow, script.replace(f"test_{name}.py", "removed.py"))
        for broken in (
            workflow.replace("runs-on: ubuntu-24.04", "runs-on: self-hosted"),
            workflow.replace("run: bash scripts/ci_run_service_integration.sh", "run: true"),
        ):
            with self.assertRaises(AssertionError):
                self.assert_service_inventory(broken, script)
        with self.assertRaises(AssertionError):
            self.assert_service_inventory(workflow, script.replace("uv run --locked --group test pytest", "# pytest"))


class RuntimeTopologyTests(unittest.TestCase):
    """完整拓扑使用本机 Cube，并与其共享文件、避开端口。"""

    def assert_hosted_jobs(self, workflow: str) -> None:
        """两个 job 均先准备真实 Cube，再启动原有应用拓扑。"""
        jobs = re.split(r"(?m)^  [\w-]+:\n", workflow.split("\njobs:\n", 1)[1])[1:]
        self.assertEqual(len(jobs), 2)
        for job in jobs:
            self.assertIn("runs-on: ubuntu-24.04", job)
            self.assertLess(job.index("python3 scripts/ci_probe_kvm.py"), job.index("bash scripts/ci_probe_hosted_cube.sh"))
            self.assertLess(job.index("bash scripts/ci_probe_hosted_cube.sh"), job.index("bash scripts/ci_prepare_system_tests_env.sh"))
            self.assertLess(job.index("bash scripts/ci_prepare_system_tests_env.sh"), job.index("docker compose up -d"))
            saves = list(re.finditer(r"(?m)^        uses: actions/cache/save@v4$", job))
            self.assertEqual(len(saves), 2)
            for save in saves:
                self.assertLess(job.index("bash scripts/ci_build_topology_images.sh"), save.start())
                self.assertLess(save.start(), job.index("docker compose up -d"))

    def test_both_runtime_jobs_use_local_cube(self):
        """实际工作流必须摆脱外部执行器与仓库 Cube 配置。"""
        workflow = (ROOT / ".github/workflows/system-tests.yml").read_text()
        self.assert_hosted_jobs(workflow)
        self.assertNotIn("vars.CUBE_", workflow)
        self.assertNotIn("secrets.CUBE_", workflow)
        for original in (
            "runs-on: ubuntu-24.04", "bash scripts/ci_probe_hosted_cube.sh", "python3 scripts/ci_probe_kvm.py",
            "uses: actions/cache/save@v4",
        ):
            for name in ("background-job-worker-path", "system-tests"):
                with self.subTest(original=original, job=name), self.assertRaises((AssertionError, ValueError)):
                    before, section = workflow.split(f"  {name}:\n", 1)
                    self.assert_hosted_jobs(before + f"  {name}:\n" + section.replace(original, "removed", 1))

    def test_environment_matches_real_compose_mounts_and_ports(self):
        """只替代宿主地址发现，用真实 Compose 展开校验容器与节点路径。"""
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / ".env.template").write_text((ROOT / ".env.template").read_text())
            docker = base / "docker"
            docker.write_text("#!/bin/sh\nprintf '%s\\n' '172.17.0.1'\n")
            docker.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if not k.startswith(("CUBE_", "YUXI_"))}
            env.pop("SILICONFLOW_API_KEY", None)
            env.update(GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted", PATH=f"{base}:{os.environ['PATH']}")
            env.update(
                JWT_SECRET_KEY="ci-jwt-secret-at-least-thirty-two-characters",
                API_KEY_DERIVATION_SECRET="ci-api-key-derivation-secret-at-least-32-chars",
            )
            subprocess.run(["bash", str(ROOT / "scripts/ci_prepare_system_tests_env.sh")], cwd=base, env=env, check=True)
            self.assertEqual((base / ".env").stat().st_mode & 0o777, 0o600)
            config = json.loads(subprocess.check_output(
                ["docker", "compose", "--env-file", str(base / ".env"), "-f", str(ROOT / "docker-compose.yml"),
                 "config", "--format", "json"],
                env={**env, "PATH": os.environ["PATH"], "YUXI_ENV_FILE": str(base / ".env")}, text=True,
            ))
            for name in ("api", "worker"):
                for key in ("SILICONFLOW_API_KEY", "WEB_SEARCH_PROVIDER", "DOUBAO_SEARCH_API_KEY", "TAVILY_API_KEY", "DEEPSEEK_API_KEY"):
                    self.assertEqual(config["services"][name]["environment"][key], "", f"{name}.{key} 必须保留模板空值")
            self.assert_shared_state(config)
            for target in ("/app/user-data", "/app/skill-projections"):
                broken = copy.deepcopy(config)
                next(m for m in broken["services"]["worker"]["volumes"] if m["target"] == target)["source"] = "/wrong-checkout"
                with self.subTest(target=target), self.assertRaises(AssertionError):
                    self.assert_shared_state(broken)
            for name, port in (
                ("redis", "6379"), ("minio", "9000"), ("minio", "9001"), ("milvus", "9091"), ("milvus", "19530"),
            ):
                broken = copy.deepcopy(config)
                next(p for p in broken["services"][name]["ports"] if p["target"] == int(port))["published"] = port
                with self.subTest(name=name, port=port), self.assertRaises(AssertionError):
                    self.assert_shared_state(broken)
            for name in ("postgres", "redis", "minio", "milvus", "graph", "api"):
                broken = copy.deepcopy(config)
                broken["services"][name]["ports"][0]["published"] = "10000"
                with self.subTest(ephemeral_port=name), self.assertRaises(AssertionError):
                    self.assert_shared_state(broken)
            original = (base / ".env").read_bytes()
            for invalid in ("", "not-an-address"):
                docker.write_text(f"#!/bin/sh\nprintf '%s\\n' '{invalid}'\n")
                result = subprocess.run(
                    ["bash", str(ROOT / "scripts/ci_prepare_system_tests_env.sh")], cwd=base, env=env,
                    capture_output=True, text=True, timeout=5,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("AddressValueError", result.stderr)
                self.assertEqual((base / ".env").read_bytes(), original)

    def assert_shared_state(self, config: dict) -> None:
        """API、worker 和 Cube metadata 必须引用同一份物理目录。"""
        for name in ("api", "worker"):
            service = config["services"][name]
            self.assertEqual(service["environment"]["CUBE_API_URL"], "http://172.17.0.1:3000")
            mappings = (("/app/user-data", "CUBE_NODE_USER_DATA_DIR"), ("/app/skill-projections", "CUBE_NODE_SKILL_PROJECTION_DIR"))
            for target, key in mappings:
                mount = next(m for m in service["volumes"] if m["target"] == target)
                self.assertEqual(mount["source"], service["environment"][key])
                self.assertTrue(mount["source"].startswith("/data/shared/"))
        for name, forbidden in (("redis", {"6379"}), ("minio", {"9000", "9001"}), ("milvus", {"9091"})):
            self.assertFalse(forbidden.intersection(str(p["published"]) for p in config["services"][name]["ports"]))
        # Cube 的宿主临时端口、沙盒映射和 SNAT 占用整个 10000–65535。
        for name in ("postgres", "redis", "minio", "milvus", "graph", "api"):
            for port in config["services"][name]["ports"]:
                self.assertLess(int(port["published"]), 10000)


if __name__ == "__main__":
    unittest.main()
