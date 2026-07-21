from datetime import datetime, timezone
import json

import httpx
import pytest

from reachpath.clients import ServiceClient
from reachpath.domain import ResearchRequest
from reachpath.orchestrator import ProspectingOrchestrator
from reachpath.settings import Settings


@pytest.mark.asyncio
async def test_real_service_contract_flow_uses_workspace_and_auth_headers() -> None:
    bundle = {
        "schema_version": "1.0",
        "bundle_id": "bundle-1",
        "research_run_id": "search-1",
        "question": "Informations professionnelles publiques sur Nadia Karim; objectif : rendez-vous",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "answer": "",
        "evidence": [],
        "claims": [],
        "usage": {},
        "warnings": [],
        "metadata": {},
    }
    dossier = {
        "schema_version": "1.0",
        "dossier_id": "argus-1",
        "status": "resolved",
        "subject": {"name": "Nadia Karim"},
        "claims": [],
        "evidence": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Workspace-ID"] == "workspace-a"
        if request.url.host == "searchswarm.test":
            assert request.headers["Authorization"] == "Bearer search-key"
            if request.method == "POST":
                assert request.headers["Idempotency-Key"].startswith("reachpath-search-")
                payload = httpx.Response(202, json={"run_id": "search-1"})
                return payload
            if request.url.path.endswith("/result"):
                return httpx.Response(200, json=bundle)
            return httpx.Response(200, json={"run_id": "search-1", "status": "completed"})
        if request.url.host == "argus.test":
            assert request.headers["X-API-Key"] == "argus-key"
            assert "bundle" in json.loads(request.content)
            return httpx.Response(200, json={"intelligence_dossier": dossier})
        if request.url.host == "reportforge.test":
            assert request.headers["Authorization"] == "Bearer report-key"
            if request.method == "POST":
                return httpx.Response(202, json={"report_run_id": "report-1", "status": "queued"})
            if request.url.path.endswith("/artifacts"):
                return httpx.Response(200, json={"items": []})
            return httpx.Response(200, json={"report_run_id": "report-1", "status": "completed"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    settings = Settings(
        dry_run=False,
        service_poll_interval_seconds=0,
        searchswarm_url="https://searchswarm.test",
        argus_url="https://argus.test",
        reportforge_url="https://reportforge.test",
        searchswarm_api_key="search-key",
        argus_api_key="argus-key",
        reportforge_api_key="report-key",
    )
    orchestrator = ProspectingOrchestrator(settings)
    orchestrator.searchswarm = ServiceClient(
        settings.searchswarm_url, settings.searchswarm_api_key, auth_mode="bearer", transport=transport
    )
    orchestrator.argus = ServiceClient(
        settings.argus_url, settings.argus_api_key, transport=transport
    )
    orchestrator.reportforge = ServiceClient(
        settings.reportforge_url,
        settings.reportforge_api_key,
        auth_mode="bearer",
        transport=transport,
    )

    result = await orchestrator.execute(
        ResearchRequest(person="Nadia Karim", objective="Obtenir un rendez-vous", dry_run=False),
        workspace_id="workspace-a",
        run_id="reachpath-1",
    )

    assert result["evidence"]["bundle_id"] == "bundle-1"
    assert result["dossier"]["dossier_id"] == "argus-1"
    assert len(result["strategies"]["scenarios"]) == 3
    assert result["report"]["report_run_id"] == "report-1"
