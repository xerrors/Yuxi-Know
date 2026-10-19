"""在临时托管执行器执行最小 KVM 客体，禁止软件模拟回退。"""

import os
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    """从串口与退出设备确认客体实际运行。"""
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("探针仅允许在 GitHub 临时托管执行器运行")
    marker = b"yuxi-kvm-guest-ok"
    code = b"\xba\xf8\x03" + b"".join(b"\xb0" + bytes([byte]) + b"\xee" for byte in marker)
    code += b"\xba\xf4\x00\xb0\x00\xee\xf4"
    with tempfile.TemporaryDirectory() as root:
        disk = Path(root) / "boot.img"
        disk.write_bytes(code.ljust(510, b"\0") + b"\x55\xaa")
        result = subprocess.run(
            [
                "sudo", "qemu-system-x86_64", "-accel", "kvm", "-cpu", "host",
                "-display", "none", "-monitor", "none", "-serial", "stdio", "-no-reboot",
                "-drive", f"file={disk},format=raw", "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
            ],
            capture_output=True, timeout=30,
        )
    if result.returncode != 1 or marker not in result.stdout:
        raise SystemExit(f"KVM 客体失败: {result.returncode}: {result.stdout!r} {result.stderr!r}")
    print(marker.decode())


if __name__ == "__main__":
    main()
