from typing import Any

import httpx


class ServiceClient:
    """Small HTTP boundary around one shared platform service."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key} if self.api_key else {}

    async def post(self, path: str, payload: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers()) as client:
            response = await client.post(path, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
