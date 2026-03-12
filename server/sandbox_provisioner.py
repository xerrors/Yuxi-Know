from __future__ import annotations

import hashlib
import os
import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException
from pydantic import BaseModel

K8S_NAMESPACE = os.environ.get("SANDBOX_K8S_NAMESPACE", "yuxi-sandbox")
SANDBOX_IMAGE = os.environ.get("SANDBOX_RUNTIME_IMAGE", "yuxi-sandbox-runtime:latest")
SANDBOX_PORT = int(os.environ.get("SANDBOX_RUNTIME_PORT", "8080"))
SERVICE_TYPE = os.environ.get("SANDBOX_K8S_SERVICE_TYPE", "ClusterIP")
SERVICE_BASE_DOMAIN = os.environ.get("SANDBOX_K8S_SERVICE_BASE_DOMAIN", "svc.cluster.local")
READY_TIMEOUT_SECONDS = int(os.environ.get("SANDBOX_K8S_READY_TIMEOUT_SECONDS", "60"))
CPU_REQUEST = os.environ.get("SANDBOX_K8S_CPU_REQUEST", "100m")
CPU_LIMIT = os.environ.get("SANDBOX_K8S_CPU_LIMIT", "1000m")
MEMORY_REQUEST = os.environ.get("SANDBOX_K8S_MEMORY_REQUEST", "256Mi")
MEMORY_LIMIT = os.environ.get("SANDBOX_K8S_MEMORY_LIMIT", "256Mi")

core_v1: k8s_client.CoreV1Api | None = None


class SandboxRequest(BaseModel):
    sandbox_id: str


class SandboxResponse(BaseModel):
    sandbox_id: str
    base_url: str
    status: str


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global core_v1
    core_v1 = _init_k8s_client()
    _ensure_namespace()
    yield


app = FastAPI(title="Yuxi Sandbox Provisioner", lifespan=lifespan)


def _init_k8s_client() -> k8s_client.CoreV1Api:
    try:
        k8s_config.load_incluster_config()
    except Exception:
        k8s_config.load_kube_config()
    return k8s_client.CoreV1Api()


def _ensure_namespace() -> None:
    assert core_v1 is not None
    try:
        core_v1.read_namespace(K8S_NAMESPACE)
    except ApiException as exc:
        if exc.status != 404:
            raise
        namespace = k8s_client.V1Namespace(metadata=k8s_client.V1ObjectMeta(name=K8S_NAMESPACE))
        core_v1.create_namespace(namespace)


def _slugify_sandbox_id(sandbox_id: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]", "-", sandbox_id.lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        normalized = "sandbox"
    digest = hashlib.sha1(sandbox_id.encode()).hexdigest()[:8]
    prefix = normalized[:40]
    return f"{prefix}-{digest}"[:49].rstrip("-")


def _pod_name(sandbox_id: str) -> str:
    return f"sandbox-{_slugify_sandbox_id(sandbox_id)}"


def _service_name(sandbox_id: str) -> str:
    return f"sandbox-{_slugify_sandbox_id(sandbox_id)}-svc"


def _service_host(service_name: str) -> str:
    return f"{service_name}.{K8S_NAMESPACE}.svc"


def _base_url(sandbox_id: str) -> str:
    service_name = _service_name(sandbox_id)
    if SERVICE_TYPE == "ClusterIP":
        return f"http://{_service_host(service_name)}:{SANDBOX_PORT}"
    return f"http://{service_name}.{K8S_NAMESPACE}.{SERVICE_BASE_DOMAIN}:{SANDBOX_PORT}"


def _build_pod(sandbox_id: str) -> k8s_client.V1Pod:
    name = _pod_name(sandbox_id)
    labels = {
        "app.kubernetes.io/name": "yuxi-sandbox",
        "app.kubernetes.io/component": "runtime",
        "sandbox-id": sandbox_id,
        "sandbox-name": name,
    }
    return k8s_client.V1Pod(
        metadata=k8s_client.V1ObjectMeta(name=name, namespace=K8S_NAMESPACE, labels=labels),
        spec=k8s_client.V1PodSpec(
            restart_policy="Never",
            containers=[
                k8s_client.V1Container(
                    name="sandbox",
                    image=SANDBOX_IMAGE,
                    image_pull_policy="IfNotPresent",
                    ports=[k8s_client.V1ContainerPort(container_port=SANDBOX_PORT, name="http")],
                    working_dir="/workspace",
                    readiness_probe=k8s_client.V1Probe(
                        http_get=k8s_client.V1HTTPGetAction(path="/health", port=SANDBOX_PORT),
                        initial_delay_seconds=1,
                        period_seconds=2,
                        timeout_seconds=2,
                        failure_threshold=15,
                    ),
                    resources=k8s_client.V1ResourceRequirements(
                        requests={"cpu": CPU_REQUEST, "memory": MEMORY_REQUEST},
                        limits={"cpu": CPU_LIMIT, "memory": MEMORY_LIMIT},
                    ),
                )
            ],
        ),
    )


def _build_service(sandbox_id: str) -> k8s_client.V1Service:
    name = _service_name(sandbox_id)
    selector = {"sandbox-name": _pod_name(sandbox_id)}
    return k8s_client.V1Service(
        metadata=k8s_client.V1ObjectMeta(
            name=name,
            namespace=K8S_NAMESPACE,
            labels={
                "app.kubernetes.io/name": "yuxi-sandbox",
                "app.kubernetes.io/component": "runtime",
                "sandbox-id": sandbox_id,
            },
        ),
        spec=k8s_client.V1ServiceSpec(
            type=SERVICE_TYPE,
            selector=selector,
            ports=[
                k8s_client.V1ServicePort(
                    name="http",
                    port=SANDBOX_PORT,
                    target_port=SANDBOX_PORT,
                    protocol="TCP",
                )
            ],
        ),
    )


def _read_sandbox_status(sandbox_id: str) -> str:
    assert core_v1 is not None
    pod = core_v1.read_namespaced_pod(_pod_name(sandbox_id), K8S_NAMESPACE)
    if pod.status.phase != "Running":
        return pod.status.phase or "Unknown"
    statuses = pod.status.container_statuses or []
    if statuses and all(status.ready for status in statuses):
        return "Running"
    return "Pending"


def _wait_until_ready(sandbox_id: str) -> str:
    deadline = time.time() + READY_TIMEOUT_SECONDS
    last_status = "Pending"
    while time.time() < deadline:
        try:
            last_status = _read_sandbox_status(sandbox_id)
        except ApiException as exc:
            if exc.status == 404:
                last_status = "NotFound"
            else:
                raise
        if last_status == "Running":
            return last_status
        time.sleep(2)
    raise HTTPException(status_code=504, detail=f"Sandbox '{sandbox_id}' not ready: {last_status}")


def _sandbox_exists(sandbox_id: str) -> bool:
    assert core_v1 is not None
    try:
        core_v1.read_namespaced_pod(_pod_name(sandbox_id), K8S_NAMESPACE)
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sandboxes", response_model=SandboxResponse)
async def create_sandbox(request: SandboxRequest) -> SandboxResponse:
    assert core_v1 is not None
    sandbox_id = request.sandbox_id

    if not _sandbox_exists(sandbox_id):
        try:
            core_v1.create_namespaced_pod(K8S_NAMESPACE, _build_pod(sandbox_id))
        except ApiException as exc:
            if exc.status != 409:
                raise HTTPException(status_code=500, detail=f"Failed to create Pod: {exc.reason}") from exc

        try:
            core_v1.create_namespaced_service(K8S_NAMESPACE, _build_service(sandbox_id))
        except ApiException as exc:
            if exc.status != 409:
                try:
                    core_v1.delete_namespaced_pod(_pod_name(sandbox_id), K8S_NAMESPACE)
                except ApiException:
                    pass
                raise HTTPException(status_code=500, detail=f"Failed to create Service: {exc.reason}") from exc

    status = _wait_until_ready(sandbox_id)
    return SandboxResponse(sandbox_id=sandbox_id, base_url=_base_url(sandbox_id), status=status)


@app.get("/sandboxes/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(sandbox_id: str) -> SandboxResponse:
    if not _sandbox_exists(sandbox_id):
        raise HTTPException(status_code=404, detail=f"Sandbox '{sandbox_id}' not found")
    status = _read_sandbox_status(sandbox_id)
    return SandboxResponse(sandbox_id=sandbox_id, base_url=_base_url(sandbox_id), status=status)


@app.delete("/sandboxes/{sandbox_id}")
async def delete_sandbox(sandbox_id: str) -> dict[str, bool | str]:
    assert core_v1 is not None

    for delete_call, name in (
        (core_v1.delete_namespaced_service, _service_name(sandbox_id)),
        (core_v1.delete_namespaced_pod, _pod_name(sandbox_id)),
    ):
        try:
            delete_call(name, K8S_NAMESPACE)
        except ApiException as exc:
            if exc.status != 404:
                raise HTTPException(status_code=500, detail=f"Failed to delete {name}: {exc.reason}") from exc

    return {"ok": True, "sandbox_id": sandbox_id}
