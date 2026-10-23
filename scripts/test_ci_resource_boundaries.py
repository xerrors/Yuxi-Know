"""验证临时托管探针拒绝普通机器及 self-hosted runner。"""

import copy
import json
import os
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

    def test_system_environment_requires_runner_temp_before_writing(self):
        """遗漏托管临时目录时拒绝，不能覆盖已有环境文件。"""
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / ".env"
            path.write_text("existing-fixture\n")
            env = {**os.environ, "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"}
            env.pop("RUNNER_TEMP", None)
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/ci_prepare_system_tests_env.sh")],
                cwd=root, env=env, capture_output=True, text=True, timeout=5, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("RUNNER_TEMP", result.stderr)
            self.assertEqual(path.read_text(), "existing-fixture\n")

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
    """常规系统拓扑使用 container，真实 Cube 只由手动探针验证。"""

    def assert_hosted_jobs(self, workflow: str) -> None:
        """两个 job 均准备 container 镜像和 runner，保留构建缓存。"""
        jobs = re.split(r"(?m)^  [\w-]+:\n", workflow.split("\njobs:\n", 1)[1])[1:]
        self.assertEqual(len(jobs), 2)
        for job in jobs:
            self.assertIn("runs-on: ubuntu-24.04", job)
            self.assertNotIn("ci_probe_kvm.py", job)
            self.assertNotIn("ci_probe_hosted_cube.sh", job)
            self.assertNotIn("test_cube_worker_recovery.sh", job)
            self.assertLess(job.index("bash scripts/ci_prepare_system_tests_env.sh"), job.index("docker compose up -d"))
            start = re.search(r"(?m)^        run: docker compose up -d (.+)$", job)
            self.assertIsNotNone(start)
            self.assertIn("sandbox-runner", shlex.split(start.group(1)))
            self.assertIn("id: sandbox-cache", job)
            saves = list(re.finditer(r"(?m)^        uses: actions/cache/save@v4$", job))
            self.assertEqual(len(saves), 3)
            for save in saves:
                self.assertLess(job.index("bash scripts/ci_build_topology_images.sh"), save.start())
                self.assertLess(save.start(), job.index("docker compose up -d"))

    def test_both_runtime_jobs_use_container(self):
        """遗漏 runner、镜像缓存或恢复真实 Cube 安装时拒绝。"""
        workflow = (ROOT / ".github/workflows/system-tests.yml").read_text()
        self.assert_hosted_jobs(workflow)
        for original in ("runs-on: ubuntu-24.04", "sandbox-runner", "id: sandbox-cache", "uses: actions/cache/save@v4"):
            for name in ("background-job-worker-path", "system-tests"):
                with self.subTest(original=original, job=name), self.assertRaises((AssertionError, ValueError)):
                    before, section = workflow.split(f"  {name}:\n", 1)
                    self.assert_hosted_jobs(before + f"  {name}:\n" + section.replace(original, "removed", 1))
        with self.assertRaises(AssertionError):
            self.assert_hosted_jobs(workflow.replace("steps:\n", "steps:\n      - run: bash scripts/ci_probe_hosted_cube.sh\n", 1))

    def test_cube_probe_only_runs_manually(self):
        """Cube 安装不能重新进入普通 push 或 PR 路径。"""
        workflow = (ROOT / ".github/workflows/cube-hosted-probe.yml").read_text()
        self.assert_manual_probe(workflow)
        for event in ("push", "pull_request", "schedule"):
            with self.subTest(event=event), self.assertRaises(AssertionError):
                self.assert_manual_probe(workflow.replace("on:\n", f"on:\n  {event}:\n"))

    def assert_manual_probe(self, workflow: str) -> None:
        """读取实际事件声明，手动入口必须保留。"""
        events = workflow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(re.findall(r"(?m)^  ([\w-]+):", events), ["workflow_dispatch"])

    def test_environment_matches_real_compose_mounts_and_runner(self):
        """执行环境生成脚本并展开真实 Compose，证明认证与挂载一致。"""
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / ".env.template").write_text((ROOT / ".env.template").read_text())
            env = {k: v for k, v in os.environ.items() if not k.startswith(("CUBE_", "YUXI_", "SANDBOX_", "COMPOSE_"))}
            env.pop("SILICONFLOW_API_KEY", None)
            env.update(GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted", RUNNER_TEMP=root)
            env.update(
                JWT_SECRET_KEY="ci-jwt-secret-at-least-thirty-two-characters",
                API_KEY_DERIVATION_SECRET="ci-api-key-derivation-secret-at-least-32-chars",
            )
            subprocess.run(["bash", str(ROOT / "scripts/ci_prepare_system_tests_env.sh")], cwd=base, env=env, check=True)
            self.assertEqual((base / ".env").stat().st_mode & 0o777, 0o600)
            config = json.loads(subprocess.check_output(
                ["docker", "compose", "--env-file", str(base / ".env"), "-f", str(ROOT / "docker-compose.yml"),
                 "config", "--format", "json"],
                env={**env, "YUXI_ENV_FILE": str(base / ".env")}, text=True,
            ))
            for name in ("api", "worker"):
                for key in ("SILICONFLOW_API_KEY", "WEB_SEARCH_PROVIDER", "DOUBAO_SEARCH_API_KEY", "TAVILY_API_KEY", "DEEPSEEK_API_KEY"):
                    self.assertEqual(config["services"][name]["environment"][key], "", f"{name}.{key} 必须保留模板空值")
            self.assert_container_state(config)
            for target in ("/app/user-data", "/app/skill-projections"):
                broken = copy.deepcopy(config)
                next(m for m in broken["services"]["worker"]["volumes"] if m["target"] == target)["source"] = "/wrong-checkout"
                with self.subTest(target=target), self.assertRaises(AssertionError):
                    self.assert_container_state(broken)
            for name in ("api", "worker"):
                broken = copy.deepcopy(config)
                broken["services"][name]["environment"]["SANDBOX_BACKEND"] = "cube"
                with self.subTest(backend=name), self.assertRaises(AssertionError):
                    self.assert_container_state(broken)
            broken = copy.deepcopy(config)
            broken["services"]["sandbox-runner"]["environment"]["SANDBOX_RUNNER_TOKEN"] = "wrong-token"
            with self.assertRaises(AssertionError):
                self.assert_container_state(broken)
            broken = copy.deepcopy(config)
            del broken["services"]["sandbox-runner"]
            with self.assertRaises(KeyError):
                self.assert_container_state(broken)

    def test_image_builder_requires_and_builds_sandbox_image(self):
        """真实 shell 必须构建 sandbox 镜像，profile 遗漏时在构建前失败。"""
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            docker = base / "docker"
            docker.write_text(
                '#!/bin/sh\n'
                'if [ "$1" = compose ]; then cat "$BUILD_CONFIG"; else printf "%s\\n" "$*" >> "$BUILD_LOG"; fi\n'
            )
            docker.chmod(0o700)
            config = {"services": {name: {"image": f"test-{name}"} for name in ("api", "minio", "storage-init", "sandbox-image")}}
            config_file = base / "config.json"
            log = base / "build.log"
            env = {
                **os.environ, "PATH": f"{base}:{os.environ['PATH']}",
                "BUILD_CONFIG": str(config_file), "BUILD_LOG": str(log),
            }
            for configured in (True, False):
                with self.subTest(configured=configured):
                    log.unlink(missing_ok=True)
                    value = copy.deepcopy(config)
                    if not configured:
                        del value["services"]["sandbox-image"]
                    config_file.write_text(json.dumps(value))
                    result = subprocess.run(
                        ["bash", str(ROOT / "scripts/ci_build_topology_images.sh"), "", "", str(base / "sandbox-cache")],
                        env=env, capture_output=True, text=True, timeout=10, check=False,
                    )
                    if not configured:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertFalse(log.exists())
                        continue
                    self.assertEqual(result.returncode, 0, result.stderr)
                    commands = [shlex.split(line) for line in log.read_text().splitlines()]
                    self.assertEqual(len(commands), 4)
                    sandbox = next(command for command in commands if "docker/sandbox.Dockerfile" in command)
                    self.assertEqual(sandbox[sandbox.index("--tag") + 1], "test-sandbox-image")
                    self.assertIn(f"type=local,dest={base}/sandbox-cache,mode=max", sandbox)
                    self.assertIn("--load", sandbox)

    def assert_container_state(self, config: dict) -> None:
        """API、worker 和 runner 共享认证与物理数据，socket 只归 runner。"""
        services = config["services"]
        runner = services["sandbox-runner"]
        token = runner["environment"]["SANDBOX_RUNNER_TOKEN"]
        self.assertGreaterEqual(len(token), 16)
        self.assertEqual(runner["environment"]["SANDBOX_CONTAINER_IMAGE"], services["sandbox-image"]["image"])
        for name in ("api", "worker"):
            service = services[name]
            self.assertEqual(service["environment"]["SANDBOX_BACKEND"], "container")
            self.assertEqual(service["environment"]["SANDBOX_RUNNER_URL"], "http://sandbox-runner:8090")
            self.assertEqual(service["environment"]["SANDBOX_RUNNER_TOKEN"], token)
            self.assertEqual(service["environment"]["CUBE_API_URL"], "")
            for target, runner_target in (("/app/user-data", "/sandbox-data"), ("/app/skill-projections", "/sandbox-skill-projections")):
                mount = next(m for m in service["volumes"] if m["target"] == target)
                runner_mount = next(m for m in runner["volumes"] if m["target"] == runner_target)
                self.assertEqual(mount["source"], runner_mount["source"])
            self.assertFalse(any(m["target"] == "/var/run/docker.sock" for m in service["volumes"]))
        self.assertTrue(any(m["target"] == "/var/run/docker.sock" for m in runner["volumes"]))


if __name__ == "__main__":
    unittest.main()
