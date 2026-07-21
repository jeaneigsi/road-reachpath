from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status

from .domain import ResearchRequest, ResearchRun, ResearchRunResponse, RunStatus
from .orchestrator import ProspectingOrchestrator
from .settings import get_settings
from .store import IdempotencyConflictError, RunStore


def _workspace(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 128:
        raise HTTPException(status_code=400, detail="X-Workspace-ID must contain 1 to 128 characters")
    return value


def _api_key_workspace(settings: Any, token: str) -> str | None:
    for entry in settings.api_keys.split(","):
        if "=" not in entry:
            continue
        configured_token, workspace = entry.split("=", 1)
        if configured_token.strip() == token:
            return workspace.strip() or None
    return None


def _response(run: ResearchRun, workspace_id: str) -> ResearchRunResponse:
    return ResearchRunResponse(
        run_id=run.id,
        workspace_id=workspace_id,
        status=run.status,
        result=run.result,
        error=run.error,
    )


async def _execute(app: FastAPI, run_id: UUID, workspace_id: str) -> None:
    store: RunStore = app.state.store
    run = store.claim(workspace_id, run_id)
    if run is None:
        return
    try:
        result = await app.state.orchestrator.execute(
            run.request,
            workspace_id=workspace_id,
            run_id=str(run_id),
        )
        store.update(workspace_id, run_id, status=RunStatus.COMPLETED, result=result)
    except Exception as exc:  # boundary converts failures to observable run state
        store.update(workspace_id, run_id, status=RunStatus.FAILED, error=str(exc))


def create_app(settings: Any | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="ReachPath API", version="0.1.0")
    app.state.settings = settings
    app.state.store = RunStore(settings.database_url)
    app.state.orchestrator = ProspectingOrchestrator(settings)

    async def workspace_context(
        workspace_header: str = Header(default="", alias="X-Workspace-ID"),
        authorization: str | None = Header(default=None, alias="Authorization"),
        api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> str:
        if not settings.require_auth:
            return _workspace(workspace_header or "local")
        token = api_key
        if not token and authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        mapped_workspace = _api_key_workspace(settings, token)
        if mapped_workspace is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if workspace_header and _workspace(workspace_header) != mapped_workspace:
            raise HTTPException(status_code=403, detail="Workspace does not match API key")
        return mapped_workspace

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "reachpath"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        try:
            app.state.store.ready()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="database unavailable") from exc
        return {"status": "ready"}

    @app.get("/v1/service")
    async def service() -> dict[str, object]:
        return {
            "name": "reachpath",
            "version": "0.1.0",
            "api_version": "v1",
            "capabilities": [
                "relationship_prospecting",
                "durable_research_runs",
                "workspace_scoping",
                "langgraph_orchestration",
            ],
        }

    @app.post(
        "/v1/research/runs",
        response_model=ResearchRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_research(
        request: ResearchRequest,
        background_tasks: BackgroundTasks,
        workspace_id: str = Depends(workspace_context),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ResearchRunResponse:
        if idempotency_key is not None:
            idempotency_key = idempotency_key.strip()
            if not idempotency_key:
                raise HTTPException(status_code=400, detail="Idempotency-Key cannot be empty")
            if len(idempotency_key) > 255:
                raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
        try:
            run, created = app.state.store.create(
                ResearchRun(request=request), workspace_id, idempotency_key
            )
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if created and app.state.settings.auto_execute:
            background_tasks.add_task(_execute, app, run.id, workspace_id)
        return _response(run, workspace_id)

    @app.get("/v1/research/runs/{run_id}", response_model=ResearchRunResponse)
    async def get_research(
        run_id: UUID,
        workspace_id: str = Depends(workspace_context),
    ) -> ResearchRunResponse:
        run = app.state.store.get(workspace_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Research run not found")
        return _response(run, workspace_id)

    @app.post("/v1/research/runs/{run_id}/cancel", response_model=ResearchRunResponse)
    async def cancel_research(
        run_id: UUID,
        workspace_id: str = Depends(workspace_context),
    ) -> ResearchRunResponse:
        run = app.state.store.get(workspace_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Research run not found")
        if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
            run = app.state.store.update(workspace_id, run_id, status=RunStatus.CANCELLED) or run
        return _response(run, workspace_id)

    return app


app = create_app()
