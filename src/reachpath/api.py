from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status

from .crm import build_argus_bundle, parse_csv
from .domain import (
    CrmImportResponse,
    ResearchRequest,
    ResearchRunListResponse,
    ResearchRun,
    ResearchRunResponse,
    RunStatus,
    UsageMetrics,
)
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
        usage=run.usage,
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
        usage = UsageMetrics.model_validate(result.get("evidence", {}).get("usage", {}) or {})
        store.update(
            workspace_id,
            run_id,
            status=RunStatus.COMPLETED,
            result=result,
            usage=usage,
        )
    except Exception as exc:  # boundary converts failures to observable run state
        store.update(workspace_id, run_id, status=RunStatus.FAILED, error=str(exc))


def create_app(settings: Any | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="ReachPath API", version="0.1.0")
    app.state.settings = settings
    app.state.store = RunStore(settings.database_url)
    app.state.orchestrator = ProspectingOrchestrator(settings)

    @app.middleware("http")
    async def request_context(request, call_next):
        import uuid

        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response

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

    @app.get("/v1/usage/quota")
    async def usage_quota(workspace_id: str = Depends(workspace_context)) -> dict[str, float | str]:
        from datetime import datetime, timezone

        consumed = app.state.store.monthly_cost(workspace_id)
        budget = float(settings.monthly_budget_usd)
        now = datetime.now(timezone.utc)
        return {
            "workspace_id": workspace_id,
            "period": f"{now.year:04d}-{now.month:02d}",
            "consumed_usd": consumed,
            "budget_usd": budget,
            "remaining_usd": max(0.0, round(budget - consumed, 6)),
        }

    @app.post("/v1/connectors/crm/import", response_model=CrmImportResponse)
    async def import_crm_csv(
        file: UploadFile = File(...),
        source_id: str = Form(..., min_length=1, max_length=255),
        owner_person_id: str = Form(..., min_length=1, max_length=255),
        owner_name: str = Form(..., min_length=2, max_length=240),
        workspace_id: str = Depends(workspace_context),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> CrmImportResponse:
        try:
            contacts = parse_csv(await file.read())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        projection: dict[str, Any] | None
        if settings.dry_run:
            projection = {"mode": "dry_run", "contacts": len(contacts)}
        else:
            try:
                projection = await app.state.orchestrator.argus.post(
                    "/v1/ingestion/bundles",
                    build_argus_bundle(contacts, source_id, owner_person_id, owner_name),
                    workspace_id=workspace_id,
                    idempotency_key=idempotency_key or f"crm-{source_id}-{workspace_id}",
                    timeout=60,
                )
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail="ARGUS CRM projection failed") from exc
        imported = app.state.store.upsert_crm_contacts(workspace_id, source_id, contacts)
        return CrmImportResponse(source_id=source_id, imported=imported, argus_projection=projection)

    @app.get("/v1/connectors/crm/contacts")
    async def list_crm_contacts(
        workspace_id: str = Depends(workspace_context),
        limit: int = 200,
    ) -> dict[str, object]:
        if not 1 <= limit <= 2_000:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")
        return {"items": app.state.store.list_crm_contacts(workspace_id, limit)}

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

    @app.get("/v1/research/runs", response_model=ResearchRunListResponse)
    async def list_research(
        workspace_id: str = Depends(workspace_context),
        limit: int = 50,
    ) -> ResearchRunListResponse:
        if not 1 <= limit <= 200:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
        return ResearchRunListResponse(
            items=[_response(run, workspace_id) for run in app.state.store.list_runs(workspace_id, limit)]
        )

    @app.get("/v1/research/runs/{run_id}", response_model=ResearchRunResponse)
    async def get_research(
        run_id: UUID,
        workspace_id: str = Depends(workspace_context),
    ) -> ResearchRunResponse:
        run = app.state.store.get(workspace_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Research run not found")
        return _response(run, workspace_id)

    async def run_artifact(run_id: UUID, workspace_id: str, key: str) -> dict[str, Any]:
        run = app.state.store.get(workspace_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Research run not found")
        if run.result is None or run.result.get(key) is None:
            raise HTTPException(status_code=409, detail="Research artifact is not ready")
        return run.result[key]

    @app.get("/v1/research/runs/{run_id}/dossier")
    async def get_dossier(
        run_id: UUID,
        workspace_id: str = Depends(workspace_context),
    ) -> dict[str, Any]:
        return await run_artifact(run_id, workspace_id, "dossier")

    @app.get("/v1/research/runs/{run_id}/strategy")
    async def get_strategy(
        run_id: UUID,
        workspace_id: str = Depends(workspace_context),
    ) -> dict[str, Any]:
        return await run_artifact(run_id, workspace_id, "strategies")

    @app.get("/v1/research/runs/{run_id}/report")
    async def get_report(
        run_id: UUID,
        workspace_id: str = Depends(workspace_context),
    ) -> dict[str, Any]:
        return await run_artifact(run_id, workspace_id, "report")

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
