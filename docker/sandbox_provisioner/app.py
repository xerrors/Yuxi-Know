from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib import request

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CreateSandboxRequest(BaseModel):
    sandbox_id: str
    thread_id: str


class SandboxResponse(BaseModel):
    sandbox_id: str
    sandbox_url: str
    status: str | None = None


class DeleteSandboxResponse(BaseModel):
    ok: bool
    sandbox_id: str


class TouchSandboxResponse(BaseModel):
    ok: bool
    sandbox_id: str
    status: str | None = None


class ListSandboxesResponse(BaseModel):
    sandboxes: list[SandboxResponse]
    count: int


@dataclass(slots=True)
class SandboxRecord:
    sandbox_id: str
    sandbox_url: str
    status: str | None = None


class MemoryProvisionerBackend:
    def __init__(self):
        self._lock = threading.Lock()
        self._records: dict[str, SandboxRecord] = {}
        self._url_template = os.getenv("MEMORY_SANDBOX_URL_TEMPLATE", "http://agent-sandbox:8000")

    def _url_for(self, sandbox_id: str) -> str:
        template = self._url_template
        if "{sandbox_id}" in template:
            return template.format(sandbox_id=sandbox_id)
        return template

    def create(self, sandbox_id: str, thread_id: str) -> SandboxRecord:
        del thread_id
        with self._lock:
            existing = self._records.get(sandbox_id)
            if existing is not None:
                return existing
            record = SandboxRecord(
                sandbox_id=sandbox_id,
                sandbox_url=self._url_for(sandbox_id),
                status="Running",
            )
            self._records[sandbox_id] = record
            return record

    def discover(self, sandbox_id: str) -> SandboxRecord | None:
        with self._lock:
            return self._records.get(sandbox_id)

    def list(self) -> list[SandboxRecord]:
        with self._lock:
            return list(self._records.values())

    def delete(self, sandbox_id: str) -> None:
        with self._lock:
            self._records.pop(sandbox_id, None)


def wait_for_sandbox_ready(sandbox_url: str, timeout_seconds: int = 30) -> bool:
    deadline = time.time() + timeout_seconds
    opener = request.build_opener(request.ProxyHandler({}))
    while time.time() < deadline:
        try:
            with opener.open(f"{sandbox_url.rstrip('/')}/v1/sandbox", timeout=3) as response:
                status_code = getattr(response, "status", 200)
            if status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


class LocalContainerProvisionerBackend:
    def __init__(self):
        import docker
        from docker.errors import DockerException

        self._docker = docker
        self._lock = threading.Lock()
        self._container_port = int(os.getenv("SANDBOX_CONTAINER_PORT", "8080"))
        self._sandbox_image = os.getenv(
            "SANDBOX_IMAGE",
            "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest",
        )
        self._network = os.getenv("DOCKER_NETWORK")
        self._threads_host_path = os.getenv("DOCKER_THREADS_HOST_PATH")
        self._skills_host_path = os.getenv("DOCKER_SKILLS_HOST_PATH")
        self._container_prefix = os.getenv("DOCKER_SANDBOX_PREFIX", "yuxi-sandbox")
        self._sandbox_host = os.getenv("DOCKER_SANDBOX_HOST", "host.docker.internal")
        self._health_timeout_seconds = int(os.getenv("SANDBOX_HEALTH_TIMEOUT_SECONDS", "30"))

        try:
            self._client = docker.from_env()
            self._client.ping()
        except DockerException as exc:
            raise RuntimeError(f"docker backend unavailable: {exc}") from exc

        self._resolve_host_paths()

    @staticmethod
    def _validate_thread_id(thread_id: str) -> str:
        candidate = str(thread_id or "").strip()
        if not candidate:
            raise ValueError("thread_id is required")
        if any(ch in candidate for ch in ("/", "\\", "\x00")):
            raise ValueError("thread_id must be a single safe path segment")
        if candidate in {".", ".."} or ".." in candidate:
            raise ValueError("thread_id contains invalid path traversal sequence")
        return candidate

    @staticmethod
    def _sanitize_id(value: str) -> str:
        sanitized = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.strip().lower())
        return sanitized[:48] or "sandbox"

    def _container_name(self, sandbox_id: str) -> str:
        return f"{self._container_prefix}-{self._sanitize_id(sandbox_id)}"

    def _resolve_host_paths(self) -> None:
        if self._threads_host_path and self._skills_host_path:
            return

        container_id = os.getenv("HOSTNAME", "").strip()
        if not container_id:
            raise RuntimeError("HOSTNAME is required to infer docker backend host paths")

        inspected = self._client.api.inspect_container(container_id)
        mounts = inspected.get("Mounts") or []

        saves_source = None
        for mount in mounts:
            destination = (mount.get("Destination") or "").rstrip("/")
            if destination == "/app/saves":
                saves_source = mount.get("Source")
                break

        if not saves_source:
            raise RuntimeError("cannot infer host path for /app/saves mount")

        base = Path(saves_source)
        if not self._threads_host_path:
            self._threads_host_path = str(base / "threads")
        if not self._skills_host_path:
            self._skills_host_path = str(base / "skills")

    def _host_port_for(self, container) -> int | None:
        ports = (container.attrs.get("NetworkSettings") or {}).get("Ports") or {}
        bindings = ports.get(f"{self._container_port}/tcp")
        if not bindings:
            return None
        host_port = bindings[0].get("HostPort")
        if not host_port:
            return None
        return int(host_port)

    def _sandbox_url(self, host_port: int) -> str:
        return f"http://{self._sandbox_host}:{host_port}"

    def _to_record(self, container, sandbox_id: str) -> SandboxRecord:
        state = (container.attrs.get("State") or {}).get("Status")
        host_port = self._host_port_for(container)
        sandbox_url = self._sandbox_url(host_port) if host_port is not None else ""
        return SandboxRecord(
            sandbox_id=sandbox_id,
            sandbox_url=sandbox_url,
            status=state or "unknown",
        )

    @staticmethod
    def _ensure_user_data_writable(container) -> None:
        cmd = (
            "sh -lc "
            "\"mkdir -p /mnt/user-data/workspace /mnt/user-data/uploads /mnt/user-data/outputs "
            "&& chmod -R a+rwX /mnt/user-data\""
        )
        result = container.exec_run(cmd, user="0:0")
        if result.exit_code != 0:
            output = result.output.decode("utf-8", errors="ignore") if isinstance(result.output, bytes) else str(result.output)
            raise RuntimeError(f"failed to ensure writable thread user-data mount: {output}")

    def _get_container(self, sandbox_id: str):
        from docker.errors import NotFound

        name = self._container_name(sandbox_id)
        try:
            return self._client.containers.get(name)
        except NotFound:
            return None

    def create(self, sandbox_id: str, thread_id: str) -> SandboxRecord:
        with self._lock:
            safe_thread_id = self._validate_thread_id(thread_id)
            existing = self._get_container(sandbox_id)
            if existing is not None:
                if existing.status != "running":
                    existing.start()
                    existing.reload()
                self._ensure_user_data_writable(existing)
                record = self._to_record(existing, sandbox_id)
                if not record.sandbox_url:
                    raise RuntimeError(f"sandbox {sandbox_id} has no mapped host port")
                if not wait_for_sandbox_ready(record.sandbox_url, timeout_seconds=self._health_timeout_seconds):
                    raise RuntimeError(f"sandbox {sandbox_id} is not ready at {record.sandbox_url}")
                return record

            threads_root = Path(self._threads_host_path).resolve()
            thread_user_data = (threads_root / safe_thread_id / "user-data").resolve()
            try:
                thread_user_data.relative_to(threads_root)
            except ValueError as exc:
                raise ValueError("thread_id resolved outside threads host root") from exc
            thread_user_data.mkdir(parents=True, exist_ok=True)

            skills_path = Path(self._skills_host_path)
            skills_path.mkdir(parents=True, exist_ok=True)

            container_name = self._container_name(sandbox_id)
            run_kwargs = {
                "name": container_name,
                "detach": True,
                "labels": {
                    "app": "yuxi-sandbox",
                    "sandbox-id": sandbox_id,
                    "thread-id": thread_id,
                    "managed-by": "yuxi-sandbox-provisioner",
                },
                "volumes": {
                    str(thread_user_data): {"bind": "/mnt/user-data", "mode": "rw"},
                    str(skills_path): {"bind": "/mnt/skills", "mode": "ro"},
                },
                "ports": {f"{self._container_port}/tcp": None},
                "security_opt": ["seccomp=unconfined"],
            }
            if self._network:
                run_kwargs["network"] = self._network

            container = self._client.containers.run(self._sandbox_image, **run_kwargs)
            container.reload()
            self._ensure_user_data_writable(container)
            record = self._to_record(container, sandbox_id)
            if not record.sandbox_url:
                raise RuntimeError(f"sandbox {sandbox_id} has no mapped host port")
            if not wait_for_sandbox_ready(record.sandbox_url, timeout_seconds=self._health_timeout_seconds):
                raise RuntimeError(f"sandbox {sandbox_id} is not ready at {record.sandbox_url}")
            return record

    def discover(self, sandbox_id: str) -> SandboxRecord | None:
        container = self._get_container(sandbox_id)
        if container is None:
            return None
        container.reload()
        record = self._to_record(container, sandbox_id)
        if not record.sandbox_url:
            return None
        if not wait_for_sandbox_ready(record.sandbox_url, timeout_seconds=5):
            return None
        return record

    def list(self) -> list[SandboxRecord]:
        containers = self._client.containers.list(
            all=True, filters={"label": ["app=yuxi-sandbox", "managed-by=yuxi-sandbox-provisioner"]}
        )
        records: list[SandboxRecord] = []
        for container in containers:
            labels = container.labels or {}
            sandbox_id = labels.get("sandbox-id")
            if sandbox_id:
                container.reload()
                records.append(self._to_record(container, sandbox_id))
        return records

    def delete(self, sandbox_id: str) -> None:
        container = self._get_container(sandbox_id)
        if container is None:
            return
        if container.status == "running":
            container.stop(timeout=10)
        container.remove(v=True, force=True)


class KubernetesProvisionerBackend:
    def __init__(self):
        from kubernetes import client, config

        self._lock = threading.Lock()
        self._namespace = os.getenv("K8S_NAMESPACE", "yuxi-know")
        self._sandbox_image = os.getenv(
            "SANDBOX_IMAGE",
            "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest",
        )
        self._skills_host_path = os.getenv("SKILLS_HOST_PATH", "/app/skills")
        self._threads_host_path = os.getenv("THREADS_HOST_PATH", "/app/saves/threads")
        self._node_host = os.getenv("NODE_HOST", "host.docker.internal")
        self._container_port = int(os.getenv("SANDBOX_CONTAINER_PORT", "8080"))

        kubeconfig_path = os.getenv("KUBECONFIG_PATH")
        if kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()

        self._core_api = client.CoreV1Api()
        self._client = client

    @staticmethod
    def _pod_name(sandbox_id: str) -> str:
        return f"sandbox-{sandbox_id}"

    @staticmethod
    def _service_name(sandbox_id: str) -> str:
        return f"sandbox-{sandbox_id}"

    def _build_pod_spec(self, sandbox_id: str, thread_id: str):
        pod_name = self._pod_name(sandbox_id)
        user_data_path = f"{self._threads_host_path.rstrip('/')}/{thread_id}/user-data"
        return self._client.V1Pod(
            metadata=self._client.V1ObjectMeta(
                name=pod_name,
                labels={"app": "yuxi-sandbox", "sandbox-id": sandbox_id},
                annotations={"thread-id": thread_id},
            ),
            spec=self._client.V1PodSpec(
                restart_policy="Never",
                containers=[
                    self._client.V1Container(
                        name="sandbox",
                        image=self._sandbox_image,
                        ports=[self._client.V1ContainerPort(container_port=self._container_port)],
                        volume_mounts=[
                            self._client.V1VolumeMount(name="user-data", mount_path="/mnt/user-data"),
                            self._client.V1VolumeMount(name="skills", mount_path="/mnt/skills", read_only=True),
                        ],
                    )
                ],
                volumes=[
                    self._client.V1Volume(
                        name="user-data",
                        host_path=self._client.V1HostPathVolumeSource(path=user_data_path, type="DirectoryOrCreate"),
                    ),
                    self._client.V1Volume(
                        name="skills",
                        host_path=self._client.V1HostPathVolumeSource(path=self._skills_host_path, type="Directory"),
                    ),
                ],
            ),
        )

    def _build_service_spec(self, sandbox_id: str):
        service_name = self._service_name(sandbox_id)
        return self._client.V1Service(
            metadata=self._client.V1ObjectMeta(
                name=service_name,
                labels={"app": "yuxi-sandbox", "sandbox-id": sandbox_id},
            ),
            spec=self._client.V1ServiceSpec(
                type="NodePort",
                selector={"sandbox-id": sandbox_id},
                ports=[
                    self._client.V1ServicePort(
                        name="http",
                        port=self._container_port,
                        target_port=self._container_port,
                        protocol="TCP",
                    )
                ],
            ),
        )

    def create(self, sandbox_id: str, thread_id: str) -> SandboxRecord:
        from kubernetes.client.rest import ApiException

        with self._lock:
            discovered = self.discover(sandbox_id)
            if discovered is not None:
                return discovered

            pod_name = self._pod_name(sandbox_id)
            service_name = self._service_name(sandbox_id)

            try:
                self._core_api.create_namespaced_pod(
                    namespace=self._namespace,
                    body=self._build_pod_spec(sandbox_id, thread_id),
                )
            except ApiException as exc:
                if exc.status != 409:
                    raise

            try:
                self._core_api.create_namespaced_service(
                    namespace=self._namespace,
                    body=self._build_service_spec(sandbox_id),
                )
            except ApiException as exc:
                if exc.status != 409:
                    raise

            record = self.discover(sandbox_id)
            if record is None:
                raise RuntimeError(f"failed to discover sandbox after create: {sandbox_id}")
            return record

    def discover(self, sandbox_id: str) -> SandboxRecord | None:
        from kubernetes.client.rest import ApiException

        pod_name = self._pod_name(sandbox_id)
        service_name = self._service_name(sandbox_id)
        try:
            pod = self._core_api.read_namespaced_pod(name=pod_name, namespace=self._namespace)
            service = self._core_api.read_namespaced_service(name=service_name, namespace=self._namespace)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

        node_port = None
        if service.spec and service.spec.ports:
            node_port = service.spec.ports[0].node_port
        if not node_port:
            sandbox_url = ""
        else:
            sandbox_url = f"http://{self._node_host}:{node_port}"

        return SandboxRecord(
            sandbox_id=sandbox_id,
            sandbox_url=sandbox_url,
            status=(pod.status.phase if pod and pod.status else "Unknown"),
        )

    def list(self) -> list[SandboxRecord]:
        from kubernetes.client.rest import ApiException

        try:
            pod_list = self._core_api.list_namespaced_pod(
                namespace=self._namespace,
                label_selector="app=yuxi-sandbox",
            )
        except ApiException:
            return []

        records: list[SandboxRecord] = []
        for pod in pod_list.items:
            sandbox_id = (pod.metadata.labels or {}).get("sandbox-id")
            if not sandbox_id:
                continue
            record = self.discover(sandbox_id)
            if record is not None:
                records.append(record)
        return records

    def delete(self, sandbox_id: str) -> None:
        from kubernetes.client.rest import ApiException

        pod_name = self._pod_name(sandbox_id)
        service_name = self._service_name(sandbox_id)

        for delete_call in (
            lambda: self._core_api.delete_namespaced_service(name=service_name, namespace=self._namespace),
            lambda: self._core_api.delete_namespaced_pod(name=pod_name, namespace=self._namespace),
        ):
            try:
                delete_call()
            except ApiException as exc:
                if exc.status != 404:
                    raise


class SandboxIdleReaper:
    def __init__(self, backend):
        self._backend = backend
        self._lock = threading.Lock()
        self._last_activity_at: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._exec_timeout_seconds = int(os.getenv("SANDBOX_EXEC_TIMEOUT_SECONDS", "180"))
        configured_idle_timeout = int(os.getenv("SANDBOX_IDLE_TIMEOUT_SECONDS", "120"))
        if 0 < configured_idle_timeout <= self._exec_timeout_seconds:
            logger.warning(
                "SANDBOX_IDLE_TIMEOUT_SECONDS=%s is <= SANDBOX_EXEC_TIMEOUT_SECONDS=%s; "
                "adjusting idle timeout to %s seconds to avoid reaping running commands",
                configured_idle_timeout,
                self._exec_timeout_seconds,
                self._exec_timeout_seconds + 30,
            )
            configured_idle_timeout = self._exec_timeout_seconds + 30
        self._idle_timeout_seconds = configured_idle_timeout
        self._check_interval_seconds = max(1, int(os.getenv("SANDBOX_IDLE_CHECK_INTERVAL_SECONDS", "10")))

    def touch(self, sandbox_id: str) -> None:
        with self._lock:
            self._last_activity_at[sandbox_id] = time.time()

    def forget(self, sandbox_id: str) -> None:
        with self._lock:
            self._last_activity_at.pop(sandbox_id, None)

    def _seed_existing(self) -> None:
        try:
            records = self._backend.list()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to seed sandbox activity for idle reaper: {exc}")
            return

        now = time.time()
        with self._lock:
            for record in records:
                self._last_activity_at.setdefault(record.sandbox_id, now)

    def _collect_expired_sandbox_ids(self) -> list[str]:
        if self._idle_timeout_seconds <= 0:
            return []
        cutoff = time.time() - self._idle_timeout_seconds
        with self._lock:
            return [sandbox_id for sandbox_id, last_at in self._last_activity_at.items() if last_at <= cutoff]

    def _run(self) -> None:
        while not self._stop_event.wait(self._check_interval_seconds):
            expired_ids = self._collect_expired_sandbox_ids()
            for sandbox_id in expired_ids:
                try:
                    self._backend.delete(sandbox_id)
                    logger.info(f"Deleted idle sandbox: {sandbox_id}")
                    self.forget(sandbox_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to delete idle sandbox {sandbox_id}: {exc}")

    def start(self) -> None:
        if self._idle_timeout_seconds <= 0:
            logger.info("Idle reaper disabled (SANDBOX_IDLE_TIMEOUT_SECONDS <= 0)")
            return
        self._seed_existing()
        self._thread = threading.Thread(target=self._run, name="sandbox-idle-reaper", daemon=True)
        self._thread.start()
        logger.info(
            "Started sandbox idle reaper with timeout=%ss interval=%ss",
            self._idle_timeout_seconds,
            self._check_interval_seconds,
        )

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)


def _build_backend():
    backend = (os.getenv("PROVISIONER_BACKEND", "memory") or "memory").strip().lower()
    if backend in {"docker", "local"}:
        return LocalContainerProvisionerBackend(), backend
    if backend == "kubernetes":
        return KubernetesProvisionerBackend(), backend
    return MemoryProvisionerBackend(), backend


backend_impl, backend_name = _build_backend()
idle_reaper = SandboxIdleReaper(backend_impl)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    idle_reaper.start()
    try:
        yield
    finally:
        idle_reaper.shutdown()


app = FastAPI(title="Yuxi Sandbox Provisioner", lifespan=lifespan)


@app.get("/health")
def health():
    tracked = len(idle_reaper._last_activity_at)  # noqa: SLF001
    return {
        "status": "ok",
        "backend": backend_name,
        "idle_timeout_seconds": idle_reaper._idle_timeout_seconds,  # noqa: SLF001
        "idle_check_interval_seconds": idle_reaper._check_interval_seconds,  # noqa: SLF001
        "tracked_sandboxes": tracked,
    }


@app.post("/api/sandboxes", response_model=SandboxResponse)
def create_sandbox(payload: CreateSandboxRequest):
    try:
        record = backend_impl.create(payload.sandbox_id, payload.thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    idle_reaper.touch(record.sandbox_id)
    return SandboxResponse(
        sandbox_id=record.sandbox_id,
        sandbox_url=record.sandbox_url,
        status=record.status,
    )


@app.get("/api/sandboxes/{sandbox_id}", response_model=SandboxResponse)
def get_sandbox(sandbox_id: str):
    try:
        record = backend_impl.discover(sandbox_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if record is None:
        raise HTTPException(status_code=404, detail="sandbox not found")
    idle_reaper.touch(record.sandbox_id)

    return SandboxResponse(
        sandbox_id=record.sandbox_id,
        sandbox_url=record.sandbox_url,
        status=record.status,
    )


@app.post("/api/sandboxes/{sandbox_id}/touch", response_model=TouchSandboxResponse)
def touch_sandbox(sandbox_id: str):
    try:
        record = backend_impl.discover(sandbox_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="sandbox not found")
    idle_reaper.touch(sandbox_id)
    return TouchSandboxResponse(ok=True, sandbox_id=sandbox_id, status=record.status)


@app.get("/api/sandboxes", response_model=ListSandboxesResponse)
def list_sandboxes():
    try:
        records = backend_impl.list()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sandboxes = [
        SandboxResponse(
            sandbox_id=record.sandbox_id,
            sandbox_url=record.sandbox_url,
            status=record.status,
        )
        for record in records
    ]
    return ListSandboxesResponse(sandboxes=sandboxes, count=len(sandboxes))


@app.delete("/api/sandboxes/{sandbox_id}", response_model=DeleteSandboxResponse)
def delete_sandbox(sandbox_id: str):
    try:
        backend_impl.delete(sandbox_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    idle_reaper.forget(sandbox_id)

    return DeleteSandboxResponse(ok=True, sandbox_id=sandbox_id)
