"""
运行 Git 变更测试的独立脚本
避免 conftest.py 的环境变量依赖
"""

import sys
import os
from pathlib import Path

# 设置项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置测试环境变量（避免 conftest.py 失败）
os.environ.setdefault("TEST_USERNAME", "test_admin")
os.environ.setdefault("TEST_PASSWORD", "test_password")

import subprocess


def run_test_file(test_file_path: str, test_name: str) -> dict:
    """运行单个测试文件并返回结果"""
    print(f"\n{'='*80}")
    print(f"正在运行: {test_name}")
    print(f"文件: {test_file_path}")
    print(f"{'='*80}\n")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file_path, "-v", "-s", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=180,
        )

        return {
            "name": test_name,
            "file": test_file_path,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "name": test_name,
            "file": test_file_path,
            "exit_code": -1,
            "stdout": "",
            "stderr": "Test timeout after 180 seconds",
            "success": False,
        }
    except Exception as e:
        return {
            "name": test_name,
            "file": test_file_path,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "success": False,
        }


def main():
    """运行所有Git变更测试"""
    print("\n" + "=" * 80)
    print("Git 变更测试套件")
    print("=" * 80)

    test_dir = Path(__file__).parent
    test_files = [
        (str(test_dir / "test_minio_client_changes.py"), "MinIO 客户端异步方法测试"),
        (str(test_dir / "test_indexing_changes.py"), "文档索引处理变更测试"),
        (str(test_dir / "test_knowledge_router_changes.py"), "知识库路由变更测试"),
    ]

    results = []
    for test_file, test_name in test_files:
        if not os.path.exists(test_file):
            print(f"\n⚠️  测试文件不存在: {test_file}")
            continue

        result = run_test_file(test_file, test_name)
        results.append(result)

        # 打印测试输出
        if result["stdout"]:
            print(result["stdout"])
        if result["stderr"]:
            print(f"\n错误输出:\n{result['stderr']}")

    # 生成测试摘要
    print("\n" + "=" * 80)
    print("测试摘要")
    print("=" * 80)

    success_count = sum(1 for r in results if r["success"])
    total_count = len(results)

    for result in results:
        status = "✓ 通过" if result["success"] else "✗ 失败"
        print(f"{status} - {result['name']}")
        if not result["success"]:
            print(f"  退出代码: {result['exit_code']}")
            if result['stderr']:
                error_preview = result['stderr'][:200].replace('\n', ' ')
                print(f"  错误: {error_preview}...")

    print(f"\n总计: {success_count}/{total_count} 测试通过")
    print("=" * 80)

    return 0 if success_count == total_count else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
