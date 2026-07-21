import httpx
import pytest

from reachpath.clients import ServiceCircuitOpenError, ServiceClient


@pytest.mark.asyncio
async def test_service_client_retries_transient_responses() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = ServiceClient(
        "https://service.test",
        transport=httpx.MockTransport(handler),
        max_retries=1,
        retry_backoff_seconds=0,
    )
    assert await client.get("/health") == {"ok": True}
    assert attempts == 2


@pytest.mark.asyncio
async def test_service_client_does_not_retry_business_errors() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(422, json={"detail": "invalid"})

    client = ServiceClient(
        "https://service.test",
        transport=httpx.MockTransport(handler),
        max_retries=3,
        retry_backoff_seconds=0,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.get("/health")
    assert attempts == 1


@pytest.mark.asyncio
async def test_service_client_opens_circuit_after_bounded_failures() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    client = ServiceClient(
        "https://service.test",
        transport=httpx.MockTransport(handler),
        max_retries=0,
        circuit_failure_threshold=1,
        circuit_cooldown_seconds=60,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.get("/health")
    with pytest.raises(ServiceCircuitOpenError):
        await client.get("/health")
    assert attempts == 1
