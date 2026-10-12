from __future__ import annotations

import hashlib
import os
import threading
import time
import weakref
from dataclasses import dataclass

from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.runtime_settings import get_int_env
from yuxi.modules.agents.runtime.sandbox.provisioner_client import ProvisionerClient, SandboxRecord
from yuxi.modules.agents.repositories.environment import AgentEnvRepository
from yuxi.modules.workspace.paths import normalize_workdir_path, workspace_uid_dirname


def sandbox_provisioner_token() -> str:
    token = os.getenv("SANDBOX_PROVISIONER_TOKEN") or ""
    if token != token.strip() or len(token) < 32:
        raise ValueError("SANDBOX_PROVISIONER_TOKEN must contain at least 32 characters")
    return token


def sandbox_id_for_thread(
    thread_id: str,
    *,
    uid: str | None = None,
) -> str:
    runtime_id = str(thread_id or "").strip()
    uid_id = str(uid or "").strip()
    identity = f"{uid_id}:{runtime_id}" if uid_id else runtime_id
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return digest[:12]


def _sandbox_key(
    uid: str,
    runtime_thread_id: str,
) -> str:
    return f"{uid}::{runtime_thread_id}"


@dataclass(slots=True)
class SandboxConnection:
    cache_key: str
    thread_id: str
    uid: str
    sandbox_id: str
    sandbox_url: str
    generation: str | None = None
    workdir_path: str | None = None


class SandboxIdentityMismatchError(RuntimeError):
    """Sandbox runtime 的持久挂载身份与请求不一致。"""


class ProvisionerSandboxProvider:
    def __init__(self):
        provider_name = (os.getenv("SANDBOX_PROVIDER") or "provisioner").strip().lower()
        if provider_name != "provisioner":
            raise ValueError("Only SANDBOX_PROVIDER=provisioner is supported.")
        provisioner_url = (os.getenv("SANDBOX_PROVISIONER_URL") or "http://sandbox-provisioner:8002").strip()

        self._client = ProvisionerClient(
            provisioner_url,
            token=sandbox_provisioner_token(),
            delete_timeout_seconds=get_int_env("SANDBOX_PROVISIONER_DELETE_TIMEOUT_SECONDS", 120),
        )
        self._lock = threading.Lock()
        # 活跃或等待中的调用者持有强引用；空闲作用域的锁自动回收。
        self._thread_locks: weakref.WeakValueDictionary[str, threading.Lock] = weakref.WeakValueDictionary()
        self._connections: dict[str, SandboxConnection] = {}
        self._last_touch_at: dict[str, float] = {}
        self._touch_interval_seconds = int(os.getenv("SANDBOX_KEEPALIVE_INTERVAL_SECONDS") or 30)

    def _thread_lock(self, cache_key: str) -> threading.Lock:
        with self._lock:
            lock = self._thread_locks.get(cache_key)
            if lock is None:
                lock = threading.Lock()
                self._thread_locks[cache_key] = lock
            return lock

    def _record_to_connection(
        self,
        *,
        cache_key: str,
        thread_id: str,
        uid: str,
        record: SandboxRecord,
    ) -> SandboxConnection:
        connection = SandboxConnection(
            cache_key=cache_key,
            thread_id=thread_id,
            uid=uid,
            sandbox_id=record.sandbox_id,
            sandbox_url=record.sandbox_url,
            generation=record.generation,
            workdir_path=record.workdir_path,
        )
        self._connections[cache_key] = connection
        self._last_touch_at[cache_key] = time.time()
        return connection

    def _should_touch(self, cache_key: str) -> bool:
        if self._touch_interval_seconds <= 0:
            return False
        last_touch = self._last_touch_at.get(cache_key)
        if last_touch is None:
            return True
        return (time.time() - last_touch) >= self._touch_interval_seconds

    def _touch_if_needed(self, connection: SandboxConnection) -> bool:
        if self._should_touch(connection.cache_key):
            is_alive = self._client.touch(connection.sandbox_id)
            self._last_touch_at[connection.cache_key] = time.time()
            if not is_alive:
                return False
        record = self._client.discover(connection.sandbox_id)
        if record is None:
            return False
        if record.workdir_path != connection.workdir_path:
            raise SandboxIdentityMismatchError("sandbox Workdir changed within one runtime scope")
        connection.sandbox_url = record.sandbox_url
        connection.generation = record.generation
        return True

    def get(
        self,
        thread_id: str,
        *,
        uid: str,
        create_if_missing: bool = False,
        inherit_env: bool = True,
        workdir_path: str | None = None,
    ) -> SandboxConnection | None:
        normalized_workdir_path = normalize_workdir_path(workdir_path) if workdir_path else None
        cache_key = _sandbox_key(uid, thread_id)
        lock = self._thread_lock(cache_key)
        with lock:
            current = self._connections.get(cache_key)
            if current:
                if current.uid != uid:
                    raise RuntimeError(f"sandbox scope {cache_key} belongs to uid {current.uid}, not {uid}")
                if current.workdir_path != normalized_workdir_path:
                    raise SandboxIdentityMismatchError("sandbox Workdir does not match the existing runtime scope")
                try:
                    if self._touch_if_needed(current):
                        return current
                    self._connections.pop(cache_key, None)
                    self._last_touch_at.pop(cache_key, None)
                except SandboxIdentityMismatchError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to touch sandbox {current.sandbox_id} for {cache_key}: {exc}")
                    return current

            sandbox_id = sandbox_id_for_thread(thread_id, uid=uid)
            if create_if_missing:
                record = self._client.create(
                    sandbox_id,
                    thread_id,
                    workspace_uid_dirname(uid),
                    AgentEnvRepository.load_for_sync_runtime(uid) if inherit_env else {},
                    workdir_path=normalized_workdir_path,
                    inherit_env=inherit_env,
                )
                if record.workdir_path != normalized_workdir_path:
                    raise RuntimeError("created sandbox Workdir does not match requested scope")
            else:
                record = self._client.discover(sandbox_id)
                if record is None:
                    return None
                if record.workdir_path != normalized_workdir_path:
                    raise RuntimeError("discovered sandbox Workdir does not match requested scope")

            return self._record_to_connection(
                cache_key=cache_key,
                thread_id=thread_id,
                uid=uid,
                record=record,
            )

    def release(
        self,
        thread_id: str,
        *,
        uid: str,
        clear_cache_on_delete_failure: bool = False,
        workdir_path: str | None = None,
    ) -> None:
        """释放一个指定作用域的 Sandbox，并清理本地连接缓存。"""
        normalized_workdir_path = normalize_workdir_path(workdir_path) if workdir_path else None
        cache_key = _sandbox_key(uid, thread_id)
        lock = self._thread_lock(cache_key)
        with lock:
            connection = self._connections.get(cache_key)
            if connection and connection.workdir_path != normalized_workdir_path:
                raise SandboxIdentityMismatchError("sandbox Workdir does not match the existing runtime scope")
            if connection is None:
                sandbox_id = sandbox_id_for_thread(thread_id, uid=uid)
                record = self._client.discover(sandbox_id)
                if record is None:
                    return
                if record.workdir_path != normalized_workdir_path:
                    raise SandboxIdentityMismatchError("sandbox Workdir does not match the requested release scope")
                generation = record.generation
            else:
                sandbox_id = connection.sandbox_id
                generation = connection.generation
            try:
                self._client.delete(sandbox_id, expected_generation=generation)
            except Exception:
                if clear_cache_on_delete_failure:
                    self._connections.pop(cache_key, None)
                    self._last_touch_at.pop(cache_key, None)
                raise
            self._connections.pop(cache_key, None)
            self._last_touch_at.pop(cache_key, None)

    def shutdown(self) -> None:
        with self._lock:
            connections = list(self._connections.values())
            self._connections.clear()
            self._last_touch_at.clear()

        for connection in connections:
            try:
                self._client.delete(
                    connection.sandbox_id,
                    expected_generation=connection.generation,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to release sandbox {connection.sandbox_id} for {connection.cache_key}: {exc}")


_sandbox_provider: ProvisionerSandboxProvider | None = None
_sandbox_provider_lock = threading.Lock()


def init_sandbox_provider() -> ProvisionerSandboxProvider:
    global _sandbox_provider
    with _sandbox_provider_lock:
        if _sandbox_provider is None:
            _sandbox_provider = ProvisionerSandboxProvider()
        return _sandbox_provider


def get_sandbox_provider() -> ProvisionerSandboxProvider:
    provider = _sandbox_provider
    if provider is not None:
        return provider
    return init_sandbox_provider()


def shutdown_sandbox_provider() -> None:
    global _sandbox_provider
    with _sandbox_provider_lock:
        provider = _sandbox_provider
        _sandbox_provider = None
    if provider is not None:
        provider.shutdown()
