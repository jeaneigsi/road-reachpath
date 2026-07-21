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


class UsageMetrics(BaseModel):
    search_calls: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)
    duration_ms: float = Field(default=0, ge=0)


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


class CrmContact(BaseModel):
    contact_id: str | None = Field(default=None, max_length=255)
    full_name: str = Field(min_length=2, max_length=240)
    email: str | None = Field(default=None, max_length=320)
    company_name: str | None = Field(default=None, max_length=240)
    company_domain: str | None = Field(default=None, max_length=255)
    job_title: str | None = Field(default=None, max_length=240)
    location: str | None = Field(default=None, max_length=240)
    relationship_strength: float = Field(default=0.7, ge=0, le=1)


class CrmContactResponse(CrmContact):
    source_id: str


class CrmImportResponse(BaseModel):
    source_id: str
    imported: int
    argus_projection: dict[str, Any] | None = None


class ResearchRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: RunStatus = RunStatus.QUEUED
    request: ResearchRequest
    result: dict[str, Any] | None = None
    error: str | None = None
    usage: UsageMetrics = Field(default_factory=UsageMetrics)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchRunResponse(BaseModel):
    run_id: UUID
    workspace_id: str
    status: RunStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    usage: UsageMetrics = Field(default_factory=UsageMetrics)


class ResearchRunListResponse(BaseModel):
    items: list[ResearchRunResponse]
