from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, status

from .domain import ResearchRequest, ResearchRun, ResearchRunResponse, RunStatus
from .orchestrator import ProspectingOrchestrator
from .settings import get_settings
from .store import RunStore


def _workspace(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 128:
        raise HTTPException(status_code=400, detail="X-Workspace-ID must contain 1 to 128 characters")
    return value


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
    run = store.get(workspace_id, run_id)
    if run is None or run.status == RunStatus.CANCELLED:
        return
    store.update(workspace_id, run_id, status=RunStatus.RUNNING)
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
    app.state.store = RunStore(settings.database_url)
    app.state.orchestrator = ProspectingOrchestrator(settings)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "reachpath"}

    @app.post(
        "/v1/research/runs",
        response_model=ResearchRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_research(
        request: ResearchRequest,
        background_tasks: BackgroundTasks,
        workspace_header: str = Header(default="local", alias="X-Workspace-ID"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ResearchRunResponse:
        workspace_id = _workspace(workspace_header)
        if idempotency_key is not None:
            idempotency_key = idempotency_key.strip()
            if not idempotency_key:
                raise HTTPException(status_code=400, detail="Idempotency-Key cannot be empty")
            if len(idempotency_key) > 255:
                raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
        run, created = app.state.store.create(
            ResearchRun(request=request), workspace_id, idempotency_key
        )
        if created:
            background_tasks.add_task(_execute, app, run.id, workspace_id)
        return _response(run, workspace_id)

    @app.get("/v1/research/runs/{run_id}", response_model=ResearchRunResponse)
    async def get_research(
        run_id: UUID,
        workspace_header: str = Header(default="local", alias="X-Workspace-ID"),
    ) -> ResearchRunResponse:
        workspace_id = _workspace(workspace_header)
        run = app.state.store.get(workspace_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Research run not found")
        return _response(run, workspace_id)

    @app.post("/v1/research/runs/{run_id}/cancel", response_model=ResearchRunResponse)
    async def cancel_research(
        run_id: UUID,
        workspace_header: str = Header(default="local", alias="X-Workspace-ID"),
    ) -> ResearchRunResponse:
        workspace_id = _workspace(workspace_header)
        run = app.state.store.get(workspace_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Research run not found")
        if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
            run = app.state.store.update(workspace_id, run_id, status=RunStatus.CANCELLED) or run
        return _response(run, workspace_id)

    return app


app = create_app()
