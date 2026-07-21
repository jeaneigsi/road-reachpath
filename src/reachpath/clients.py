import asyncio
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
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.auth_mode = auth_mode
        self.transport = transport
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)

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
            return await self._request(client, "POST", path, timeout, json=payload)

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
            return await self._request(client, "GET", path, timeout)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        timeout: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.request(method, path, timeout=timeout, **kwargs)
            except httpx.TransportError:
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("Service request retry loop ended unexpectedly")
