from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from .domain import ResearchRequest, ResearchRun, RunStatus


class Base(DeclarativeBase):
    pass


class ResearchRunRecord(Base):
    __tablename__ = "research_runs"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(4_000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunStore:
    """Durable run repository with workspace scoping.

    SQLite is the local default; production uses the same repository with a
    PostgreSQL SQLAlchemy URL.
    """

    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        kwargs: dict[str, Any] = {"connect_args": connect_args, "pool_pre_ping": True}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
        self.engine = create_engine(database_url, **kwargs)
        Base.metadata.create_all(self.engine)

    def create(
        self,
        run: ResearchRun,
        workspace_id: str,
        idempotency_key: str | None,
    ) -> tuple[ResearchRun, bool]:
        with Session(self.engine) as session:
            if idempotency_key:
                existing = session.scalar(
                    select(ResearchRunRecord).where(
                        ResearchRunRecord.workspace_id == workspace_id,
                        ResearchRunRecord.idempotency_key == idempotency_key,
                    )
                )
                if existing is not None:
                    return self._to_domain(existing), False
            record = ResearchRunRecord(
                id=str(run.id),
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                status=run.status.value,
                request_json=run.request.model_dump(mode="json"),
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
            session.add(record)
            session.commit()
            return self._to_domain(record), True

    def get(self, workspace_id: str, run_id: UUID) -> ResearchRun | None:
        with Session(self.engine) as session:
            record = session.scalar(
                select(ResearchRunRecord).where(
                    ResearchRunRecord.workspace_id == workspace_id,
                    ResearchRunRecord.id == str(run_id),
                )
            )
            return self._to_domain(record) if record else None

    def update(
        self,
        workspace_id: str,
        run_id: UUID,
        *,
        status: RunStatus | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ResearchRun | None:
        with Session(self.engine) as session:
            record = session.scalar(
                select(ResearchRunRecord).where(
                    ResearchRunRecord.workspace_id == workspace_id,
                    ResearchRunRecord.id == str(run_id),
                )
            )
            if record is None:
                return None
            if status is not None:
                record.status = status.value
            if result is not None:
                record.result_json = result
            if error is not None:
                record.error = error
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._to_domain(record)

    @staticmethod
    def _to_domain(record: ResearchRunRecord) -> ResearchRun:
        return ResearchRun(
            id=UUID(record.id),
            status=RunStatus(record.status),
            request=ResearchRequest.model_validate(record.request_json),
            result=record.result_json,
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
