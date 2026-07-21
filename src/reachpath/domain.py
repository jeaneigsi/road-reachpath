from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_CLARIFICATION = "needs_clarification"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchRequest(BaseModel):
    person: str = Field(min_length=2, max_length=240)
    company: str | None = Field(default=None, max_length=240)
    objective: str = Field(min_length=3, max_length=2_000)
    location: str | None = Field(default=None, max_length=240)
    locale: str = Field(default="fr", min_length=2, max_length=20)
    max_search_calls: int = Field(default=8, ge=1, le=100)
    max_results: int = Field(default=20, ge=1, le=200)
    dry_run: bool | None = None
    max_cost_usd: float = Field(default=1.0, gt=0, le=100)
    max_duration_seconds: int = Field(default=300, gt=0, le=86_400)


class ResearchRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: RunStatus = RunStatus.QUEUED
    request: ResearchRequest
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchRunResponse(BaseModel):
    run_id: UUID
    workspace_id: str
    status: RunStatus
    result: dict[str, Any] | None = None
    error: str | None = None
