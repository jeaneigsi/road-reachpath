from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, HTTPException, status

from .domain import ResearchRequest, ResearchRun, ResearchRunResponse, RunStatus
from .orchestrator import ProspectingOrchestrator
from .settings import get_settings

app = FastAPI(title="ReachPath API", version="0.1.0")
_runs: dict[UUID, ResearchRun] = {}
_orchestrator = ProspectingOrchestrator(get_settings())


async def _execute(run_id: UUID) -> None:
    run = _runs[run_id]
    run.status = RunStatus.RUNNING
    try:
        run.result = await _orchestrator.execute(run.request)
        run.status = RunStatus.COMPLETED
    except Exception as exc:  # boundary converts failures to observable run state
        run.error = str(exc)
        run.status = RunStatus.FAILED


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "reachpath"}


@app.post("/v1/research/runs", response_model=ResearchRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_research(request: ResearchRequest, background_tasks: BackgroundTasks) -> ResearchRunResponse:
    run = ResearchRun(request=request)
    _runs[run.id] = run
    background_tasks.add_task(_execute, run.id)
    return ResearchRunResponse(run_id=run.id, status=run.status)


@app.get("/v1/research/runs/{run_id}", response_model=ResearchRunResponse)
async def get_research(run_id: UUID) -> ResearchRunResponse:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return ResearchRunResponse(run_id=run.id, status=run.status, result=run.result, error=run.error)


@app.post("/v1/research/runs/{run_id}/cancel", response_model=ResearchRunResponse)
async def cancel_research(run_id: UUID) -> ResearchRunResponse:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
        run.status = RunStatus.CANCELLED
    return ResearchRunResponse(run_id=run.id, status=run.status, result=run.result, error=run.error)
