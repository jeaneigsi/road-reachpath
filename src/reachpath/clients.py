from typing import Any, Literal

import httpx


class ServiceClient:
    """Small HTTP boundary around one shared platform service."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        auth_mode: Literal["x-api-key", "bearer"] = "x-api-key",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.auth_mode = auth_mode
        self.transport = transport

    def headers(
        self,
        *,
        workspace_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            if self.auth_mode == "bearer":
                headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                headers["X-API-Key"] = self.api_key
        if workspace_id:
            headers["X-Workspace-ID"] = workspace_id
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        workspace_id: str | None = None,
        idempotency_key: str | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers(workspace_id=workspace_id, idempotency_key=idempotency_key),
            transport=self.transport,
        ) as client:
            response = await client.post(path, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()

    async def get(
        self,
        path: str,
        *,
        workspace_id: str | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers(workspace_id=workspace_id),
            transport=self.transport,
        ) as client:
            response = await client.get(path, timeout=timeout)
            response.raise_for_status()
            return response.json()
