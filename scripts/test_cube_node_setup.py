"""验证嵌套节点安装入口只修改 host.quota，并拒绝未知布局。"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BASE = '''other:
  enabled: true
host:
  quota:
    mcpu_limit: 0
    mem_limit: ""
    mvm_limit: 0
    creation_concurrent_num: 0
    paused_resource_release_ratio: 0.0
  gc:
    creation_concurrent_num: 99
'''

EXPECTED = '''other:
  enabled: true
host:
  quota:
    mcpu_limit: 128000
    mem_limit: "128Gi"
    mvm_limit: 512
    creation_concurrent_num: 4
    paused_resource_release_ratio: 1.0
  gc:
    creation_concurrent_num: 99
'''


class CubeNodeSetupTest(unittest.TestCase):
    """在临时文件中执行实际安装脚本的配额编辑代码。"""

    def run_editor(self, content: str) -> tuple[subprocess.CompletedProcess, str]:
        """替换固定配置路径，不执行安装或节点重启。"""
        script = Path(__file__).resolve().parents[1] / 'docker/cube/setup-node.sh'
        code = script.read_text().split("    python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'conf.yaml'
            config.write_text(content)
            code = code.replace('/usr/local/services/cubetoolbox/Cubelet/dynamicconf/conf.yaml', str(config))
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
            return result, config.read_text()

    def test_updates_only_quota_and_is_idempotent(self):
        """同名兄弟字段保持原值，重复配置得到相同结果。"""
        for source in (BASE, EXPECTED):
            with self.subTest(source=source):
                result, content = self.run_editor(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(content, EXPECTED)

    def test_rejects_unknown_layout_without_writing(self):
        """缺段、缺字段及重复字段在正确原因上失败且不改文件。"""
        cases = [
            (BASE.replace('host:', 'another:'), '缺少 host 段'),
            (BASE.replace('  quota:', '  wrong:'), '缺少 host.quota 段'),
            (BASE.replace('    mvm_limit: 0\n', ''), '配额字段数量异常：mvm_limit'),
            (BASE.replace('    mvm_limit: 0\n', '    mvm_limit: 0\n    mvm_limit: 1\n'), '配额字段数量异常：mvm_limit'),
        ]
        for source, error in cases:
            with self.subTest(error=error):
                result, content = self.run_editor(source)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)
                self.assertEqual(content, source)


if __name__ == '__main__':
    unittest.main()
