from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from .crm import build_argus_bundle, parse_csv
from .domain import (
    ApiKeyCreateRequest,
    ApiKeyResponse,
    AuditEventResponse,
    CrmImportResponse,
    ResearchClarificationRequest,
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


def _token_from_headers(authorization: str | None, api_key: str | None) -> str | None:
    if api_key:
        return api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _response(run: ResearchRun, workspace_id: str) -> ResearchRunResponse:
    return ResearchRunResponse(
        run_id=run.id,
        workspace_id=workspace_id,
        request=run.request,
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
        budget = float(app.state.settings.monthly_budget_usd)
        consumed = store.monthly_cost(workspace_id)
        if consumed >= budget:
            store.update(
                workspace_id,
                run_id,
                status=RunStatus.FAILED,
                error="Monthly workspace budget exhausted before execution",
            )
            store.record_audit(
                workspace_id,
                "research.budget_exhausted",
                "research_run",
                str(run_id),
            )
            return
        result = await app.state.orchestrator.execute(
            run.request,
            workspace_id=workspace_id,
            run_id=str(run_id),
        )
        usage = UsageMetrics.model_validate(result.get("usage") or {})
        dossier_status = str((result.get("dossier") or {}).get("status", "")).lower()
        run_status = (
            RunStatus.NEEDS_CLARIFICATION
            if dossier_status in {"ambiguous", "needs_review", "not_found"}
            else RunStatus.COMPLETED
        )
        store.update(
            workspace_id,
            run_id,
            status=run_status,
            result=result,
            usage=usage,
        )
        store.record_audit(
            workspace_id,
            "research.status_changed",
            "research_run",
            str(run_id),
            {"status": run_status.value},
        )
    except Exception as exc:  # boundary converts failures to observable run state
        store.update(workspace_id, run_id, status=RunStatus.FAILED, error=str(exc))
        store.record_audit(
            workspace_id,
            "research.failed",
            "research_run",
            str(run_id),
            {"error": str(exc)[:500]},
        )


def create_app(settings: Any | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="ReachPath API", version="0.1.0")
    cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-API-Key", "X-Workspace-ID"],
    )
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
        token = _token_from_headers(authorization, api_key)
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        mapped_workspace = app.state.store.api_key_workspace(token) or _api_key_workspace(settings, token)
        if mapped_workspace is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if workspace_header and _workspace(workspace_header) != mapped_workspace:
            raise HTTPException(status_code=403, detail="Workspace does not match API key")
        return mapped_workspace

    async def admin_context(
        workspace_id: str = Depends(workspace_context),
        authorization: str | None = Header(default=None, alias="Authorization"),
        api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> str:
        if not settings.require_auth:
            return workspace_id
        token = _token_from_headers(authorization, api_key)
        allowed = {entry.strip() for entry in settings.admin_api_keys.split(",") if entry.strip()}
        if token not in allowed and app.state.store.api_key_role(token or "") != "admin":
            raise HTTPException(status_code=403, detail="Admin API key required")
        return workspace_id

    async def role_context(
        workspace_id: str = Depends(workspace_context),
        authorization: str | None = Header(default=None, alias="Authorization"),
        api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> str:
        if not settings.require_auth:
            return "admin"
        token = _token_from_headers(authorization, api_key)
        role = app.state.store.api_key_role(token or "")
        return role or "operator"

    async def operator_context(
        workspace_id: str = Depends(workspace_context),
        role: str = Depends(role_context),
    ) -> str:
        if role not in {"operator", "admin"}:
            raise HTTPException(status_code=403, detail="Operator role required")
        return workspace_id

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

    @app.post("/v1/admin/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
    async def create_api_key(
        payload: ApiKeyCreateRequest,
        workspace_id: str = Depends(admin_context),
    ) -> ApiKeyResponse:
        response = app.state.store.create_api_key(workspace_id, payload.name, payload.role)
        app.state.store.record_audit(
            workspace_id, "api_key.created", "api_key", response.key_id, {"role": payload.role.value}
        )
        return response

    @app.post("/v1/admin/api-keys/{key_id}/rotate", response_model=ApiKeyResponse)
    async def rotate_api_key(
        key_id: str,
        workspace_id: str = Depends(admin_context),
    ) -> ApiKeyResponse:
        response = app.state.store.rotate_api_key(workspace_id, key_id)
        if response is None:
            raise HTTPException(status_code=404, detail="API key not found")
        app.state.store.record_audit(workspace_id, "api_key.rotated", "api_key", key_id)
        return response

    @app.delete("/v1/admin/api-keys/{key_id}")
    async def revoke_api_key(
        key_id: str,
        workspace_id: str = Depends(admin_context),
    ) -> dict[str, bool]:
        if not app.state.store.revoke_api_key(workspace_id, key_id):
            raise HTTPException(status_code=404, detail="API key not found")
        app.state.store.record_audit(workspace_id, "api_key.revoked", "api_key", key_id)
        return {"revoked": True}

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

    @app.get("/v1/audit/events", response_model=list[AuditEventResponse])
    async def audit_events(
        workspace_id: str = Depends(workspace_context),
        limit: int = 200,
    ) -> list[AuditEventResponse]:
        if not 1 <= limit <= 2_000:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")
        return app.state.store.list_audit_events(workspace_id, limit)

    @app.get("/v1/audit/export", response_model=list[AuditEventResponse])
    async def audit_export(
        workspace_id: str = Depends(workspace_context),
    ) -> list[AuditEventResponse]:
        return app.state.store.list_audit_events(workspace_id, 2_000)

    @app.get("/v1/privacy/people/{person_name}/export")
    async def privacy_export(
        person_name: str,
        workspace_id: str = Depends(workspace_context),
    ) -> dict[str, Any]:
        result = app.state.store.privacy_export(workspace_id, person_name)
        app.state.store.record_audit(
            workspace_id, "privacy.exported", "person", person_name
        )
        return result

    @app.delete("/v1/privacy/people/{person_name}")
    async def privacy_delete(
        person_name: str,
        workspace_id: str = Depends(operator_context),
    ) -> dict[str, Any]:
        deleted = app.state.store.privacy_delete(workspace_id, person_name)
        app.state.store.record_audit(
            workspace_id, "privacy.deleted", "person", person_name, deleted
        )
        return {"workspace_id": workspace_id, "person": person_name, "deleted": deleted}

    @app.post("/v1/connectors/crm/import", response_model=CrmImportResponse)
    async def import_crm_csv(
        file: UploadFile = File(...),
        source_id: str = Form(..., min_length=1, max_length=255),
        owner_person_id: str = Form(..., min_length=1, max_length=255),
        owner_name: str = Form(..., min_length=2, max_length=240),
        workspace_id: str = Depends(operator_context),
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
        app.state.store.record_audit(
            workspace_id,
            "crm.imported",
            "crm_source",
            source_id,
            {"imported": imported},
        )
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
        workspace_id: str = Depends(operator_context),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ResearchRunResponse:
        budget = float(settings.monthly_budget_usd)
        consumed = app.state.store.monthly_cost(workspace_id)
        remaining = round(budget - consumed, 6)
        if remaining <= 0 or request.max_cost_usd > remaining:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "monthly_budget_exceeded",
                    "budget_usd": budget,
                    "consumed_usd": consumed,
                    "remaining_usd": max(0.0, remaining),
                    "requested_max_cost_usd": request.max_cost_usd,
                },
            )
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
        app.state.store.record_audit(
            workspace_id,
            "research.created" if created else "research.replayed",
            "research_run",
            str(run.id),
        )
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
        workspace_id: str = Depends(operator_context),
    ) -> ResearchRunResponse:
        run = app.state.store.get(workspace_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Research run not found")
        if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
            run = app.state.store.update(workspace_id, run_id, status=RunStatus.CANCELLED) or run
            app.state.store.record_audit(workspace_id, "research.cancelled", "research_run", str(run_id))
        return _response(run, workspace_id)

    @app.post(
        "/v1/research/runs/{run_id}/clarify",
        response_model=ResearchRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def clarify_research(
        run_id: UUID,
        request: ResearchClarificationRequest,
        background_tasks: BackgroundTasks,
        workspace_id: str = Depends(operator_context),
    ) -> ResearchRunResponse:
        run = app.state.store.requeue_with_request(workspace_id, run_id, request)
        if run is None:
            raise HTTPException(
                status_code=409,
                detail="Research run is not awaiting clarification",
            )
        if app.state.settings.auto_execute:
            background_tasks.add_task(_execute, app, run.id, workspace_id)
        app.state.store.record_audit(workspace_id, "research.clarified", "research_run", str(run_id))
        return _response(run, workspace_id)

    return app


app = create_app()
