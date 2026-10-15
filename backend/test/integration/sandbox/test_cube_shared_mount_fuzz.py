"""可重放的共享文件压力与普通用户命令 fuzz，回读宿主字节。"""

import hashlib
import json
import random
import shlex
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from yuxi.modules.workspace.paths import user_workspace_dir

pytestmark = [pytest.mark.integration, pytest.mark.self_managed_resources, pytest.mark.timeout(300)]

FILE_PROGRAM = """import hashlib,json,os,sys
from pathlib import Path
job=json.loads(sys.argv[1])
root=Path(job['directory'])
root.mkdir(parents=True,exist_ok=True)
assert Path('pause-marker').read_text()==job['marker']
for item in job['files']:
    if 'previous_digest' in item:
        assert hashlib.sha256((root/item['name']).read_bytes()).hexdigest()==item['previous_digest']
for iteration in range(3):
    for item in job['files']:
        path=root/item['name']
        pattern=bytes.fromhex(item['pattern'])
        content=(pattern*((job['size']+len(pattern)-1)//len(pattern)))[:job['size']]
        temporary=path.with_name(path.name+'.next')
        with temporary.open('wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        assert path.read_bytes()==content
print(json.dumps({'files':len(job['files']),'writes':3*len(job['files'])}))
"""


@pytest.mark.parametrize(
    ("seed", "workers", "size"),
    [(17, 1, 4096), (42, 2, 65536), (20261015, 4, 262144), (20261016, 8, 1048576)],
)
def test_seeded_shared_io_survives_pause_resume(resources, seed, workers, size, record_property):
    """并发写读和原子替换跨休眠继续，身份和宿主字节保持一致。"""
    uid, _, provider, backend = resources
    reference = provider.get(uid)
    generation = provider.status(uid)["generation"]
    root = user_workspace_dir(uid)
    names = [
        "plain.bin",
        "space name.bin",
        "资料.bin",
        "quote'\".bin",
        "semi;$.bin",
        "-leading.bin",
        "brackets[0].bin",
        "newline\nname.bin",
    ]
    rng = random.Random(seed)
    phases = []
    previous_digests = {}

    for phase in range(2):
        marker = f"host-{seed}-{phase}"
        (root / "pause-marker").write_text(marker)
        jobs = [
            {
                "directory": f"worker-{worker}",
                "marker": marker,
                "size": size,
                "files": [{"name": name, "pattern": rng.randbytes(32).hex()} for name in names],
            }
            for worker in range(workers)
        ]
        for job in jobs:
            for item in job["files"]:
                key = (job["directory"], item["name"])
                if phase:
                    item["previous_digest"] = previous_digests[key]
                pattern = bytes.fromhex(item["pattern"])
                expected = (pattern * ((size + len(pattern) - 1) // len(pattern)))[:size]
                previous_digests[key] = hashlib.sha256(expected).hexdigest()

        def execute(job):
            """记录完整执行边界的延迟，并核对真正退出码。"""
            started = time.perf_counter()
            command = f"python3 -c {shlex.quote(FILE_PROGRAM)} {shlex.quote(json.dumps(job))}"
            response = backend.execute(command, timeout=120)
            assert response.exit_code == 0, (seed, phase, job["directory"], response.output)
            assert json.loads(response.output) == {"files": len(names), "writes": 3 * len(names)}
            return (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        with ThreadPoolExecutor(workers) as pool:
            latencies = list(pool.map(execute, jobs))
        elapsed = time.perf_counter() - started
        for job in jobs:
            for item in job["files"]:
                actual = (root / job["directory"] / item["name"]).read_bytes()
                assert hashlib.sha256(actual).hexdigest() == previous_digests[(job["directory"], item["name"])], (
                    seed,
                    phase,
                    job["directory"],
                    item["name"],
                )
        assert provider.status(uid)["active_operations"] == 0
        assert provider.get(uid).sandbox_id == reference.sandbox_id
        assert provider.status(uid)["generation"] == generation
        phases.append(
            {
                "phase": "running" if phase == 0 else "resumed",
                "seconds": round(elapsed, 3),
                "median_ms": round(statistics.median(latencies), 3),
                "max_ms": round(max(latencies), 3),
                "write_mib_per_second": round(workers * len(names) * 3 * size / elapsed / 1048576, 3),
            }
        )
        provider.adapter.pause(reference)
        assert provider.adapter.state(reference).lower() == "paused"

    result = {"seed": seed, "workers": workers, "file_bytes": size, "files_per_worker": len(names), "phases": phases}
    record_property("sandbox_io_fuzz", json.dumps(result))
    print(json.dumps(result))


def test_resume_oracle_rejects_missing_previous_file(resources):
    """丢失休眠前文件时必须先失败，不能用重写掩盖丢失。"""
    uid, _, provider, backend = resources
    root = user_workspace_dir(uid)
    (root / "pause-marker").write_text("negative")
    job = {
        "directory": "guard",
        "marker": "negative",
        "size": 32,
        "files": [{"name": "lost.bin", "pattern": "01", "previous_digest": hashlib.sha256(b"prior").hexdigest()}],
    }
    response = backend.execute(f"python3 -c {shlex.quote(FILE_PROGRAM)} {shlex.quote(json.dumps(job))}", timeout=30)
    assert response.exit_code == 1 and "FileNotFoundError" in response.output
    assert not (root / "guard" / "lost.bin").exists()
    assert provider.status(uid)["active_operations"] == 0


@pytest.mark.parametrize("seed", [97, 20261015])
def test_seeded_command_output_and_exit_codes(resources, seed, record_property):
    """并发混合正常与非零退出，不遗留句柄且不混淆输出归属。"""
    uid, _, provider, backend = resources
    reference = provider.get(uid)
    rng = random.Random(seed)
    jobs = [(f"case {index}: 资料 ' \" ; $ {rng.getrandbits(64)}\n", rng.choice([0, 1, 7, 31, 143])) for index in range(32)]

    def execute(job):
        """命令文本由引用后的测试数据生成，返回真实延迟。"""
        text, exit_code = job
        started = time.perf_counter()
        response = backend.execute(f"printf %s {shlex.quote(text)}; exit {exit_code}", timeout=30)
        assert (response.output, response.exit_code) == (text, exit_code), (seed, job, response)
        return (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with ThreadPoolExecutor(4) as pool:
        latencies = list(pool.map(execute, jobs))
    assert provider.status(uid)["active_operations"] == 0
    assert provider.get(uid).sandbox_id == reference.sandbox_id
    result = {
        "seed": seed,
        "commands": len(jobs),
        "workers": 4,
        "seconds": round(time.perf_counter() - started, 3),
        "median_ms": round(statistics.median(latencies), 3),
        "max_ms": round(max(latencies), 3),
    }
    record_property("sandbox_command_fuzz", json.dumps(result))
    print(json.dumps(result))
