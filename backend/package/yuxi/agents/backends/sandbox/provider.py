from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

from yuxi import config as conf
from yuxi.utils.logging_config import logger

from .provisioner_client import ProvisionerClient, SandboxRecord


def sandbox_id_for_thread(thread_id: str) -> str:
    digest = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()
    return digest[:12]


@dataclass(slots=True)
class SandboxConnection:
    thread_id: str
    user_id: str
    sandbox_id: str
    sandbox_url: str


class ProvisionerSandboxProvider:
    def __init__(self):
        provider_name = str(getattr(conf, "sandbox_provider", "provisioner")).strip().lower()
        if provider_name != "provisioner":
            raise RuntimeError("only sandbox_provider=provisioner is supported")

        provisioner_url = str(getattr(conf, "sandbox_provisioner_url", "") or "").strip()
        if not provisioner_url:
            raise RuntimeError("sandbox_provisioner_url is required")

        self._client = ProvisionerClient(provisioner_url)
        self._lock = threading.Lock()
        self._thread_locks: dict[str, threading.Lock] = {}
        self._connections: dict[str, SandboxConnection] = {}
        self._last_touch_at: dict[str, float] = {}
        self._touch_interval_seconds = int(getattr(conf, "sandbox_keepalive_interval_seconds", 30))

    def _thread_lock(self, thread_id: str) -> threading.Lock:
        with self._lock:
            lock = self._thread_locks.get(thread_id)
            if lock is None:
                lock = threading.Lock()
                self._thread_locks[thread_id] = lock
            return lock

    def _record_to_connection(self, thread_id: str, user_id: str, record: SandboxRecord) -> SandboxConnection:
        connection = SandboxConnection(
            thread_id=thread_id,
            user_id=user_id,
            sandbox_id=record.sandbox_id,
            sandbox_url=record.sandbox_url,
        )
        self._connections[thread_id] = connection
        self._last_touch_at[thread_id] = time.time()
        return connection

    def _should_touch(self, thread_id: str) -> bool:
        if self._touch_interval_seconds <= 0:
            return False
        last_touch = self._last_touch_at.get(thread_id)
        if last_touch is None:
            return True
        return (time.time() - last_touch) >= self._touch_interval_seconds

    def _touch_if_needed(self, connection: SandboxConnection) -> bool:
        if not self._should_touch(connection.thread_id):
            return True
        is_alive = self._client.touch(connection.sandbox_id)
        self._last_touch_at[connection.thread_id] = time.time()
        return is_alive

    def acquire(self, thread_id: str, *, user_id: str) -> str:
        lock = self._thread_lock(thread_id)
        with lock:
            current = self._connections.get(thread_id)
            if current:
                try:
                    if self._touch_if_needed(current):
                        return current.sandbox_id
                    self._connections.pop(thread_id, None)
                    self._last_touch_at.pop(thread_id, None)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to touch sandbox {current.sandbox_id} for thread {thread_id}: {exc}")
                    return current.sandbox_id

            sandbox_id = sandbox_id_for_thread(thread_id)
            record = self._client.discover(sandbox_id)
            if record is None:
                logger.info(f"Creating sandbox {sandbox_id} for thread {thread_id}")
                record = self._client.create(sandbox_id, thread_id, user_id)
            else:
                logger.info(f"Reusing sandbox {sandbox_id} for thread {thread_id}")

            connection = self._record_to_connection(thread_id, user_id, record)
            return connection.sandbox_id

    def get(self, thread_id: str, *, user_id: str, create_if_missing: bool = False) -> SandboxConnection | None:
        lock = self._thread_lock(thread_id)
        with lock:
            current = self._connections.get(thread_id)
            if current:
                try:
                    if self._touch_if_needed(current):
                        return current
                    self._connections.pop(thread_id, None)
                    self._last_touch_at.pop(thread_id, None)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to touch sandbox {current.sandbox_id} for thread {thread_id}: {exc}")
                    return current
                if current.user_id == user_id:
                    return current
                self._connections.pop(thread_id, None)
                self._last_touch_at.pop(thread_id, None)

            sandbox_id = sandbox_id_for_thread(thread_id)
            record = self._client.discover(sandbox_id)
            if record is None:
                if not create_if_missing:
                    return None
                record = self._client.create(sandbox_id, thread_id, user_id)

            return self._record_to_connection(thread_id, user_id, record)

    def shutdown(self) -> None:
        with self._lock:
            connections = list(self._connections.values())
            self._connections.clear()
            self._last_touch_at.clear()

        for connection in connections:
            try:
                self._client.delete(connection.sandbox_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"Failed to release sandbox {connection.sandbox_id} for thread {connection.thread_id}: {exc}"
                )


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
