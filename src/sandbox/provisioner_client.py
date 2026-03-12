from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class ProvisionedSandbox:
    sandbox_id: str
    base_url: str
    status: str | None = None


class ProvisionerClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def create_sandbox(self, sandbox_id: str) -> ProvisionedSandbox:
        response = self._request("POST", "/sandboxes", json={"sandbox_id": sandbox_id})
        return self._parse_sandbox(response.json())

    def get_sandbox(self, sandbox_id: str) -> ProvisionedSandbox | None:
        response = self._request(
            "GET",
            f"/sandboxes/{sandbox_id}",
            allow_not_found=True,
        )
        if response is None:
            return None
        return self._parse_sandbox(response.json())

    def delete_sandbox(self, sandbox_id: str) -> None:
        self._request(
            "DELETE",
            f"/sandboxes/{sandbox_id}",
            allow_not_found=True,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response | None:
        try:
            with httpx.Client(base_url=self._base_url, timeout=self._timeout) as client:
                response = client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Provisioner request failed: {exc}") from exc

        if allow_not_found and response.status_code == 404:
            return None

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Provisioner request failed: {exc.response.status_code} {exc.response.text}"
            ) from exc

        return response

    @staticmethod
    def _parse_sandbox(data: dict) -> ProvisionedSandbox:
        base_url = data.get("base_url") or data.get("sandbox_url")
        if not base_url:
            raise RuntimeError("Provisioner response missing base_url")
        return ProvisionedSandbox(
            sandbox_id=data["sandbox_id"],
            base_url=base_url,
            status=data.get("status"),
        )
