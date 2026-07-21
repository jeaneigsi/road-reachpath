import asyncio
from time import monotonic
from typing import Any, Literal

import httpx


class ServiceCircuitOpenError(RuntimeError):
    """Raised while a downstream service is in its cooldown window."""


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
        circuit_failure_threshold: int = 3,
        circuit_cooldown_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.auth_mode = auth_mode
        self.transport = transport
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.circuit_failure_threshold = max(1, circuit_failure_threshold)
        self.circuit_cooldown_seconds = max(0.0, circuit_cooldown_seconds)
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None

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
        self._check_circuit()
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.request(method, path, timeout=timeout, **kwargs)
            except httpx.TransportError:
                if attempt >= self.max_retries:
                    self._record_failure()
                    raise
                await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
                continue
            if response.status_code in {429, 500, 502, 503, 504}:
                self._record_failure()
            else:
                self._record_success()
            response.raise_for_status()
            return response.json()
        raise RuntimeError("Service request retry loop ended unexpectedly")

    def _check_circuit(self) -> None:
        if self._circuit_opened_at is None:
            return
        if monotonic() - self._circuit_opened_at < self.circuit_cooldown_seconds:
            raise ServiceCircuitOpenError(f"Downstream service circuit open for {self.base_url}")
        self._circuit_opened_at = None
        self._consecutive_failures = 0

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.circuit_failure_threshold:
            self._circuit_opened_at = monotonic()

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_opened_at = None
