from __future__ import annotations

import asyncio
import time
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .clients import ServiceClient
from .domain import ResearchRequest
from .settings import Settings


class ResearchState(TypedDict, total=False):
    request: dict[str, Any]
    workspace_id: str
    run_id: str
    evidence: dict[str, Any]
    dossier: dict[str, Any]
    report: dict[str, Any]


class ProspectingOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.searchswarm = ServiceClient(
            settings.searchswarm_url,
            settings.searchswarm_api_key,
            auth_mode="bearer",
        )
        self.argus = ServiceClient(settings.argus_url, settings.argus_api_key)
        self.reportforge = ServiceClient(
            settings.reportforge_url,
            settings.reportforge_api_key,
            auth_mode="bearer",
        )

    def _is_dry_run(self, request: dict[str, Any]) -> bool:
        requested = request.get("dry_run")
        return self.settings.dry_run if requested is None else bool(requested)

    @staticmethod
    def _question(request: dict[str, Any]) -> str:
        parts = [f"Informations professionnelles publiques sur {request['person']}"]
        if request.get("company"):
            parts.append(f"entreprise : {request['company']}")
        if request.get("location"):
            parts.append(f"localisation : {request['location']}")
        parts.append(f"objectif : {request['objective']}")
        return "; ".join(parts)

    def _graph(self):
        graph = StateGraph(ResearchState)
        graph.add_node("collect", self._collect)
        graph.add_node("analyze", self._analyze)
        graph.add_node("compose", self._compose)
        graph.set_entry_point("collect")
        graph.add_edge("collect", "analyze")
        graph.add_edge("analyze", "compose")
        graph.add_edge("compose", END)
        return graph.compile()

    async def _collect(self, state: ResearchState) -> dict[str, Any]:
        request = state["request"]
        if self._is_dry_run(request):
            return {"evidence": {"mode": "dry_run", "sources": []}}
        payload = {
            "question": self._question(request),
            "mode": "balanced",
            "locale": request.get("locale", "fr"),
            "max_search_calls": request["max_search_calls"] if "max_search_calls" in request else 8,
            "max_results": request["max_results"] if "max_results" in request else 20,
            "max_cost_usd": request["max_cost_usd"],
            "max_duration_seconds": request["max_duration_seconds"],
            "metadata": {"reachpath_run_id": state.get("run_id"), "person": request["person"]},
        }
        created = await self.searchswarm.post(
            "/v1/research/runs",
            payload,
            workspace_id=state.get("workspace_id"),
            idempotency_key=f"reachpath-search-{state.get('run_id', request['person'])}",
            timeout=30,
        )
        search_run_id = created.get("run_id")
        if not search_run_id:
            raise RuntimeError("SearchSwarm response did not contain run_id")
        deadline = time.monotonic() + request["max_duration_seconds"]
        while True:
            snapshot = await self.searchswarm.get(
                f"/v1/research/runs/{search_run_id}",
                workspace_id=state.get("workspace_id"),
                timeout=30,
            )
            status = str(snapshot.get("status", "")).lower()
            if status == "completed":
                bundle = await self.searchswarm.get(
                    f"/v1/research/runs/{search_run_id}/result",
                    workspace_id=state.get("workspace_id"),
                    timeout=30,
                )
                return {"evidence": bundle, "search_snapshot": snapshot}
            if status in {"failed", "cancelled"}:
                raise RuntimeError(snapshot.get("error_message") or f"SearchSwarm run {status}")
            if time.monotonic() >= deadline:
                raise TimeoutError("SearchSwarm research exceeded the requested duration")
            await asyncio.sleep(self.settings.service_poll_interval_seconds)

    async def _analyze(self, state: ResearchState) -> dict[str, Any]:
        if self._is_dry_run(state["request"]):
            request = state["request"]
            return {
                "dossier": {
                    "target": {"name": request["person"], "company": request.get("company")},
                    "identity_confidence": 0.0,
                    "relationship_paths": [],
                    "contact_points": [],
                    "limitations": ["Simulation locale : aucune source externe interrogée."],
                }
            }
        request = state["request"]
        result = await self.argus.post(
            "/v1/research/evidence-bundles",
            {
                "bundle": state["evidence"],
                "source_person": request["person"],
                "purpose": "b2b_sales",
                "max_duration_seconds": request["max_duration_seconds"],
            },
            workspace_id=state.get("workspace_id"),
            idempotency_key=f"reachpath-argus-{state.get('run_id', request['person'])}",
            timeout=request["max_duration_seconds"],
        )
        return {"dossier": result.get("intelligence_dossier", result), "argus_result": result}

    async def _compose(self, state: ResearchState) -> dict[str, Any]:
        if self._is_dry_run(state["request"]):
            request = state["request"]
            return {
                "report": {
                    "title": f"Dossier de prospection — {request['person']}",
                    "objective": request["objective"],
                    "scenarios": [],
                    "sources": state["evidence"].get("sources", []),
                }
            }
        request = state["request"]
        dossier = state["dossier"]
        result = await self.reportforge.post(
            "/api/v1/report-jobs",
            {
                "schema_version": "1.0",
                "title": f"Dossier de prospection — {request['person']}",
                "objective": request["objective"],
                "dossier": dossier,
                "audience": "Business development",
                "locale": request.get("locale", "fr"),
                "metadata": {"reachpath_run_id": state.get("run_id")},
            },
            workspace_id=state.get("workspace_id"),
            idempotency_key=f"reachpath-report-{state.get('run_id', request['person'])}",
            timeout=30,
        )
        report_run_id = result.get("report_run_id")
        if not report_run_id:
            return {"report": result}
        deadline = time.monotonic() + request["max_duration_seconds"]
        while True:
            snapshot = await self.reportforge.get(
                f"/api/v1/report-jobs/{report_run_id}",
                workspace_id=state.get("workspace_id"),
                timeout=30,
            )
            status = str(snapshot.get("status", "")).lower()
            if status in {"completed", "published", "failed", "cancelled", "error"}:
                return {"report": snapshot}
            if time.monotonic() >= deadline:
                raise TimeoutError("ReportForge job exceeded the requested duration")
            await asyncio.sleep(self.settings.service_poll_interval_seconds)

    async def execute(
        self,
        request: ResearchRequest,
        *,
        workspace_id: str = "local",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        result = await self._graph().ainvoke(
            {
                "request": request.model_dump(),
                "workspace_id": workspace_id,
                "run_id": run_id,
            }
        )
        return {"evidence": result.get("evidence"), "dossier": result.get("dossier"), "report": result.get("report")}
