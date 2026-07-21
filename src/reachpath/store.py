from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import secrets
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from .domain import (
    CrmContact,
    CrmContactResponse,
    ApiKeyResponse,
    ResearchRequest,
    ResearchRun,
    RunStatus,
    UsageMetrics,
)


class Base(DeclarativeBase):
    pass


class ApiKeyRecord(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("key_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(24))
    key_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchRunRecord(Base):
    __tablename__ = "research_runs"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(4_000), nullable=True)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CrmContactRecord(Base):
    __tablename__ = "crm_contacts"
    __table_args__ = (UniqueConstraint("workspace_id", "source_id", "contact_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    contact_id: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(240))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    location: Mapped[str | None] = mapped_column(String(240), nullable=True)
    relationship_strength: Mapped[float] = mapped_column()
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
                    if existing.request_hash != self._request_hash(run.request):
                        raise IdempotencyConflictError(
                            "Idempotency-Key was already used with a different request"
                        )
                    return self._to_domain(existing), False
            record = ResearchRunRecord(
                id=str(run.id),
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                request_hash=self._request_hash(run.request),
                status=run.status.value,
                request_json=run.request.model_dump(mode="json"),
                usage_json=run.usage.model_dump(mode="json"),
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
            session.add(record)
            session.commit()
            return self._to_domain(record), True

    @staticmethod
    def _request_hash(request: ResearchRequest) -> str:
        payload = json.dumps(
            request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def get(self, workspace_id: str, run_id: UUID) -> ResearchRun | None:
        with Session(self.engine) as session:
            record = session.scalar(
                select(ResearchRunRecord).where(
                    ResearchRunRecord.workspace_id == workspace_id,
                    ResearchRunRecord.id == str(run_id),
                )
            )
            return self._to_domain(record) if record else None

    def list_runs(self, workspace_id: str, limit: int = 50) -> list[ResearchRun]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(ResearchRunRecord)
                .where(ResearchRunRecord.workspace_id == workspace_id)
                .order_by(ResearchRunRecord.created_at.desc())
                .limit(limit)
            ).all()
            return [self._to_domain(record) for record in records]

    def claim(self, workspace_id: str, run_id: UUID) -> ResearchRun | None:
        """Atomically claim a queued run for one API task or worker."""
        with Session(self.engine) as session:
            record = session.scalar(
                select(ResearchRunRecord).where(
                    ResearchRunRecord.workspace_id == workspace_id,
                    ResearchRunRecord.id == str(run_id),
                    ResearchRunRecord.status == RunStatus.QUEUED.value,
                )
            )
            if record is None:
                return None
            record.status = RunStatus.RUNNING.value
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._to_domain(record)

    def queued(self, limit: int = 20) -> list[tuple[str, UUID]]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(ResearchRunRecord)
                .where(ResearchRunRecord.status == RunStatus.QUEUED.value)
                .order_by(ResearchRunRecord.created_at)
                .limit(limit)
            ).all()
            return [(record.workspace_id, UUID(record.id)) for record in records]

    def ready(self) -> None:
        with self.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")

    @staticmethod
    def _key_hash(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    def api_key_workspace(self, token: str) -> str | None:
        with Session(self.engine) as session:
            record = session.scalar(
                select(ApiKeyRecord).where(
                    ApiKeyRecord.key_hash == self._key_hash(token),
                    ApiKeyRecord.revoked_at.is_(None),
                )
            )
            return record.workspace_id if record else None

    def create_api_key(self, workspace_id: str, name: str) -> ApiKeyResponse:
        token = f"rp_{secrets.token_urlsafe(32)}"
        now = datetime.now(timezone.utc)
        record = ApiKeyRecord(
            id=str(uuid4()),
            workspace_id=workspace_id,
            name=name,
            prefix=token[:12],
            key_hash=self._key_hash(token),
            created_at=now,
        )
        with Session(self.engine, expire_on_commit=False) as session:
            session.add(record)
            session.commit()
        return self._api_key_response(record, token)

    def rotate_api_key(self, workspace_id: str, key_id: str) -> ApiKeyResponse | None:
        with Session(self.engine, expire_on_commit=False) as session:
            record = session.scalar(
                select(ApiKeyRecord).where(
                    ApiKeyRecord.id == key_id,
                    ApiKeyRecord.workspace_id == workspace_id,
                    ApiKeyRecord.revoked_at.is_(None),
                )
            )
            if record is None:
                return None
            record.revoked_at = datetime.now(timezone.utc)
            token = f"rp_{secrets.token_urlsafe(32)}"
            replacement = ApiKeyRecord(
                id=str(uuid4()),
                workspace_id=workspace_id,
                name=record.name,
                prefix=token[:12],
                key_hash=self._key_hash(token),
                created_at=datetime.now(timezone.utc),
            )
            session.add(replacement)
            session.commit()
            return self._api_key_response(replacement, token)

    def revoke_api_key(self, workspace_id: str, key_id: str) -> bool:
        with Session(self.engine) as session:
            record = session.scalar(
                select(ApiKeyRecord).where(
                    ApiKeyRecord.id == key_id,
                    ApiKeyRecord.workspace_id == workspace_id,
                    ApiKeyRecord.revoked_at.is_(None),
                )
            )
            if record is None:
                return False
            record.revoked_at = datetime.now(timezone.utc)
            session.commit()
            return True

    @staticmethod
    def _api_key_response(record: ApiKeyRecord, token: str | None = None) -> ApiKeyResponse:
        return ApiKeyResponse(
            key_id=record.id,
            workspace_id=record.workspace_id,
            name=record.name,
            prefix=record.prefix,
            created_at=record.created_at,
            revoked_at=record.revoked_at,
            key=token,
        )

    def upsert_crm_contacts(
        self, workspace_id: str, source_id: str, contacts: list[CrmContact]
    ) -> int:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            for index, contact in enumerate(contacts):
                contact_id = contact.contact_id or f"row-{index + 2}"
                record = session.scalar(
                    select(CrmContactRecord).where(
                        CrmContactRecord.workspace_id == workspace_id,
                        CrmContactRecord.source_id == source_id,
                        CrmContactRecord.contact_id == contact_id,
                    )
                )
                if record is None:
                    record = CrmContactRecord(
                        id=f"{workspace_id}:{source_id}:{contact_id}",
                        workspace_id=workspace_id,
                        source_id=source_id,
                        contact_id=contact_id,
                        created_at=now,
                    )
                    session.add(record)
                record.full_name = contact.full_name
                record.email = contact.email
                record.company_name = contact.company_name
                record.company_domain = contact.company_domain
                record.job_title = contact.job_title
                record.location = contact.location
                record.relationship_strength = contact.relationship_strength
                record.updated_at = now
            session.commit()
        return len(contacts)

    def list_crm_contacts(self, workspace_id: str, limit: int = 200) -> list[CrmContactResponse]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(CrmContactRecord)
                .where(CrmContactRecord.workspace_id == workspace_id)
                .order_by(CrmContactRecord.updated_at.desc())
                .limit(limit)
            ).all()
            return [
                CrmContactResponse(
                    contact_id=record.contact_id,
                    full_name=record.full_name,
                    email=record.email,
                    company_name=record.company_name,
                    company_domain=record.company_domain,
                    job_title=record.job_title,
                    location=record.location,
                    relationship_strength=record.relationship_strength,
                    source_id=record.source_id,
                )
                for record in records
            ]

    def update(
        self,
        workspace_id: str,
        run_id: UUID,
        *,
        status: RunStatus | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        usage: UsageMetrics | None = None,
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
            if usage is not None:
                record.usage_json = usage.model_dump(mode="json")
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._to_domain(record)

    def monthly_cost(self, workspace_id: str) -> float:
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        with Session(self.engine) as session:
            records = session.scalars(
                select(ResearchRunRecord).where(
                    ResearchRunRecord.workspace_id == workspace_id,
                    ResearchRunRecord.created_at >= start,
                )
            ).all()
            return round(sum(float((record.usage_json or {}).get("cost_usd", 0)) for record in records), 6)

    @staticmethod
    def _to_domain(record: ResearchRunRecord) -> ResearchRun:
        return ResearchRun(
            id=UUID(record.id),
            status=RunStatus(record.status),
            request=ResearchRequest.model_validate(record.request_json),
            result=record.result_json,
            error=record.error,
            usage=UsageMetrics.model_validate(record.usage_json or {}),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class IdempotencyConflictError(ValueError):
    """An idempotency key cannot be reused for a different request."""
