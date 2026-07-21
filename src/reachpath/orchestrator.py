from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .clients import ServiceClient
from .domain import ResearchRequest
from .settings import Settings


class ResearchState(TypedDict, total=False):
    request: dict[str, Any]
    evidence: dict[str, Any]
    dossier: dict[str, Any]
    report: dict[str, Any]


class ProspectingOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.searchswarm = ServiceClient(settings.searchswarm_url, settings.searchswarm_api_key)
        self.argus = ServiceClient(settings.argus_url, settings.argus_api_key)
        self.reportforge = ServiceClient(settings.reportforge_url, settings.reportforge_api_key)

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
        if self.settings.dry_run:
            return {"evidence": {"mode": "dry_run", "sources": []}}
        result = await self.searchswarm.post("/v1/research/runs", request)
        return {"evidence": result}

    async def _analyze(self, state: ResearchState) -> dict[str, Any]:
        if self.settings.dry_run:
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
        result = await self.argus.post("/v1/intelligence/ask", state["request"])
        return {"dossier": result}

    async def _compose(self, state: ResearchState) -> dict[str, Any]:
        if self.settings.dry_run:
            request = state["request"]
            return {
                "report": {
                    "title": f"Dossier de prospection — {request['person']}",
                    "objective": request["objective"],
                    "scenarios": [],
                    "sources": state["evidence"].get("sources", []),
                }
            }
        result = await self.reportforge.post("/api/v1/report-jobs", state["dossier"])
        return {"report": result}

    async def execute(self, request: ResearchRequest) -> dict[str, Any]:
        result = await self._graph().ainvoke({"request": request.model_dump()})
        return {"evidence": result.get("evidence"), "dossier": result.get("dossier"), "report": result.get("report")}
