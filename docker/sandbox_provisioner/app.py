from __future__ import annotations

import os
import threading
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


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


class KubernetesProvisionerBackend:
    def __init__(self):
        from kubernetes import client, config

        self._lock = threading.Lock()
        self._namespace = os.getenv("K8S_NAMESPACE", "yuxi-know")
        self._sandbox_image = os.getenv("SANDBOX_IMAGE", "ghcr.io/bytedance/deer-flow-sandbox:latest")
        self._skills_host_path = os.getenv("SKILLS_HOST_PATH", "/app/skills")
        self._threads_host_path = os.getenv("THREADS_HOST_PATH", "/app/saves/threads")
        self._node_host = os.getenv("NODE_HOST", "host.docker.internal")
        self._container_port = int(os.getenv("SANDBOX_CONTAINER_PORT", "8000"))

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


def _build_backend():
    backend = (os.getenv("PROVISIONER_BACKEND", "memory") or "memory").strip().lower()
    if backend == "kubernetes":
        return KubernetesProvisionerBackend(), backend
    return MemoryProvisionerBackend(), backend


app = FastAPI(title="Yuxi Sandbox Provisioner")
backend_impl, backend_name = _build_backend()


@app.get("/health")
def health():
    return {"status": "ok", "backend": backend_name}


@app.post("/api/sandboxes", response_model=SandboxResponse)
def create_sandbox(payload: CreateSandboxRequest):
    try:
        record = backend_impl.create(payload.sandbox_id, payload.thread_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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

    return SandboxResponse(
        sandbox_id=record.sandbox_id,
        sandbox_url=record.sandbox_url,
        status=record.status,
    )


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

    return DeleteSandboxResponse(ok=True, sandbox_id=sandbox_id)
