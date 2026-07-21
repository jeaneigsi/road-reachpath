from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import secrets
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, JSON, DateTime, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from .domain import (
    CrmContact,
    CrmContactResponse,
    CrmConnectionResponse,
    CrmProvider,
    WebhookSubscriptionResponse,
    ApiKeyResponse,
    ApiKeyRole,
    AuditEventResponse,
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
    role: Mapped[str] = mapped_column(String(20), default=ApiKeyRole.OPERATOR.value)
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


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CrmOAuthStateRecord(Base):
    __tablename__ = "crm_oauth_states"
    __table_args__ = (UniqueConstraint("state_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    state_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrmConnectionRecord(Base):
    __tablename__ = "crm_connections"
    __table_args__ = (UniqueConstraint("workspace_id", "provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(32), default="connected")
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    access_token_enc: Mapped[str] = mapped_column(String(10_000))
    refresh_token_enc: Mapped[str | None] = mapped_column(String(10_000), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WebhookSubscriptionRecord(Base):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    url: Mapped[str] = mapped_column(String(2_000))
    events_json: Mapped[list[str]] = mapped_column(JSON)
    secret_enc: Mapped[str] = mapped_column(String(10_000))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunStore:
    """Durable run repository with workspace scoping.

    SQLite is the local default; production uses the same repository with a
    PostgreSQL SQLAlchemy URL.
    """

    def __init__(self, database_url: str, *, create_schema: bool = True) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        kwargs: dict[str, Any] = {"connect_args": connect_args, "pool_pre_ping": True}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
        self.engine = create_engine(database_url, **kwargs)
        if create_schema:
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
            connection.exec_driver_sql("SELECT 1 FROM research_runs LIMIT 1")

    def record_audit(
        self,
        workspace_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEventResponse:
        event = AuditEventRecord(
            id=str(uuid4()),
            workspace_id=workspace_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        with Session(self.engine, expire_on_commit=False) as session:
            session.add(event)
            session.commit()
        return self._audit_response(event)

    def create_oauth_state(
        self, workspace_id: str, provider: str, ttl_seconds: int
    ) -> tuple[str, datetime]:
        state = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        record = CrmOAuthStateRecord(
            id=str(uuid4()),
            workspace_id=workspace_id,
            provider=provider,
            state_hash=self._key_hash(state),
            expires_at=expires_at,
        )
        with Session(self.engine) as session:
            session.add(record)
            session.commit()
        return state, expires_at

    def consume_oauth_state(self, provider: str, state: str) -> tuple[str, datetime] | None:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            record = session.scalar(
                select(CrmOAuthStateRecord).where(
                    CrmOAuthStateRecord.provider == provider,
                    CrmOAuthStateRecord.state_hash == self._key_hash(state),
                    CrmOAuthStateRecord.used_at.is_(None),
                    CrmOAuthStateRecord.expires_at > now,
                )
            )
            if record is None:
                return None
            record.used_at = now
            session.commit()
            return record.workspace_id, record.expires_at

    def upsert_crm_connection(
        self,
        workspace_id: str,
        provider: str,
        *,
        access_token_enc: str,
        refresh_token_enc: str | None,
        external_account_id: str | None,
        api_domain: str | None,
        scope: str | None,
        expires_at: datetime | None,
    ) -> CrmConnectionResponse:
        now = datetime.now(timezone.utc)
        with Session(self.engine, expire_on_commit=False) as session:
            record = session.scalar(
                select(CrmConnectionRecord).where(
                    CrmConnectionRecord.workspace_id == workspace_id,
                    CrmConnectionRecord.provider == provider,
                )
            )
            if record is None:
                record = CrmConnectionRecord(
                    id=str(uuid4()),
                    workspace_id=workspace_id,
                    provider=provider,
                    created_at=now,
                )
                session.add(record)
            record.status = "connected"
            record.access_token_enc = access_token_enc
            record.refresh_token_enc = refresh_token_enc
            record.external_account_id = external_account_id
            record.api_domain = api_domain
            record.scope = scope
            record.expires_at = expires_at
            record.updated_at = now
            session.commit()
            return self._crm_connection_response(record)

    def list_crm_connections(self, workspace_id: str) -> list[CrmConnectionResponse]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(CrmConnectionRecord)
                .where(CrmConnectionRecord.workspace_id == workspace_id)
                .order_by(CrmConnectionRecord.updated_at.desc())
            ).all()
            return [self._crm_connection_response(record) for record in records]

    def get_crm_connection_secret(
        self, workspace_id: str, connection_id: str
    ) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            record = session.scalar(
                select(CrmConnectionRecord).where(
                    CrmConnectionRecord.workspace_id == workspace_id,
                    CrmConnectionRecord.id == connection_id,
                )
            )
            if record is None:
                return None
            return {
                "connection_id": record.id,
                "provider": record.provider,
                "access_token_enc": record.access_token_enc,
                "refresh_token_enc": record.refresh_token_enc,
                "external_account_id": record.external_account_id,
                "api_domain": record.api_domain,
                "scope": record.scope,
                "expires_at": record.expires_at,
            }

    def update_crm_connection_tokens(
        self,
        workspace_id: str,
        connection_id: str,
        *,
        access_token_enc: str,
        refresh_token_enc: str | None,
        expires_at: datetime | None,
    ) -> CrmConnectionResponse | None:
        with Session(self.engine, expire_on_commit=False) as session:
            record = session.scalar(
                select(CrmConnectionRecord).where(
                    CrmConnectionRecord.workspace_id == workspace_id,
                    CrmConnectionRecord.id == connection_id,
                )
            )
            if record is None:
                return None
            record.access_token_enc = access_token_enc
            record.refresh_token_enc = refresh_token_enc
            record.expires_at = expires_at
            record.status = "connected"
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._crm_connection_response(record)

    def delete_crm_connection(self, workspace_id: str, connection_id: str) -> bool:
        with Session(self.engine) as session:
            record = session.scalar(
                select(CrmConnectionRecord).where(
                    CrmConnectionRecord.workspace_id == workspace_id,
                    CrmConnectionRecord.id == connection_id,
                )
            )
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    @staticmethod
    def _crm_connection_response(record: CrmConnectionRecord) -> CrmConnectionResponse:
        return CrmConnectionResponse(
            connection_id=record.id,
            provider=CrmProvider(record.provider),
            status=record.status,
            external_account_id=record.external_account_id,
            api_domain=record.api_domain,
            scope=record.scope,
            expires_at=record.expires_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def list_audit_events(self, workspace_id: str, limit: int = 200) -> list[AuditEventResponse]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(AuditEventRecord)
                .where(AuditEventRecord.workspace_id == workspace_id)
                .order_by(AuditEventRecord.created_at.desc())
                .limit(limit)
            ).all()
            return [self._audit_response(record) for record in records]

    @staticmethod
    def _audit_response(record: AuditEventRecord) -> AuditEventResponse:
        return AuditEventResponse(
            event_id=record.id,
            workspace_id=record.workspace_id,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            metadata=record.metadata_json or {},
            created_at=record.created_at,
        )

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

    def api_key_role(self, token: str) -> str | None:
        with Session(self.engine) as session:
            record = session.scalar(
                select(ApiKeyRecord).where(
                    ApiKeyRecord.key_hash == self._key_hash(token),
                    ApiKeyRecord.revoked_at.is_(None),
                )
            )
            return record.role if record else None

    def create_api_key(
        self, workspace_id: str, name: str, role: ApiKeyRole = ApiKeyRole.OPERATOR
    ) -> ApiKeyResponse:
        token = f"rp_{secrets.token_urlsafe(32)}"
        now = datetime.now(timezone.utc)
        record = ApiKeyRecord(
            id=str(uuid4()),
            workspace_id=workspace_id,
            name=name,
            role=role.value,
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
                role=record.role,
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
            role=ApiKeyRole(record.role),
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

    def privacy_export(self, workspace_id: str, person_name: str) -> dict[str, Any]:
        target = person_name.strip().casefold()
        with Session(self.engine) as session:
            runs = session.scalars(
                select(ResearchRunRecord).where(ResearchRunRecord.workspace_id == workspace_id)
            ).all()
            contacts = session.scalars(
                select(CrmContactRecord).where(CrmContactRecord.workspace_id == workspace_id)
            ).all()
            matching_runs = []
            for record in runs:
                if str((record.request_json or {}).get("person", "")).casefold() != target:
                    continue
                run = self._to_domain(record).model_dump(mode="json")
                run["run_id"] = run.pop("id")
                matching_runs.append(run)
            matching_contacts = [
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
                ).model_dump(mode="json")
                for record in contacts
                if record.full_name.casefold() == target
            ]
        return {
            "workspace_id": workspace_id,
            "person": person_name,
            "research_runs": matching_runs,
            "crm_contacts": matching_contacts,
        }

    def privacy_delete(self, workspace_id: str, person_name: str) -> dict[str, int]:
        target = person_name.strip().casefold()
        deleted_runs = 0
        deleted_contacts = 0
        with Session(self.engine) as session:
            runs = session.scalars(
                select(ResearchRunRecord).where(ResearchRunRecord.workspace_id == workspace_id)
            ).all()
            for record in runs:
                if str((record.request_json or {}).get("person", "")).casefold() == target:
                    session.delete(record)
                    deleted_runs += 1
            contacts = session.scalars(
                select(CrmContactRecord).where(CrmContactRecord.workspace_id == workspace_id)
            ).all()
            for record in contacts:
                if record.full_name.casefold() == target:
                    session.delete(record)
                    deleted_contacts += 1
            session.commit()
        return {"research_runs": deleted_runs, "crm_contacts": deleted_contacts}

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

    def requeue_with_request(
        self, workspace_id: str, run_id: UUID, request: ResearchRequest
    ) -> ResearchRun | None:
        """Replace an ambiguous request and make the same run executable again."""
        with Session(self.engine) as session:
            record = session.scalar(
                select(ResearchRunRecord).where(
                    ResearchRunRecord.workspace_id == workspace_id,
                    ResearchRunRecord.id == str(run_id),
                    ResearchRunRecord.status == RunStatus.NEEDS_CLARIFICATION.value,
                )
            )
            if record is None:
                return None
            record.request_json = request.model_dump(mode="json")
            record.request_hash = self._request_hash(request)
            record.status = RunStatus.QUEUED.value
            record.result_json = None
            record.error = None
            record.usage_json = UsageMetrics().model_dump(mode="json")
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

    def purge_research_runs(self, workspace_id: str, older_than_days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        removable = {
            RunStatus.COMPLETED.value,
            RunStatus.NEEDS_CLARIFICATION.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }
        deleted = 0
        with Session(self.engine) as session:
            records = session.scalars(
                select(ResearchRunRecord).where(
                    ResearchRunRecord.workspace_id == workspace_id,
                    ResearchRunRecord.updated_at < cutoff,
                    ResearchRunRecord.status.in_(removable),
                )
            ).all()
            for record in records:
                session.delete(record)
                deleted += 1
            session.commit()
        return deleted

    def create_webhook(
        self, workspace_id: str, url: str, events: list[str], secret_enc: str
    ) -> WebhookSubscriptionResponse:
        now = datetime.now(timezone.utc)
        record = WebhookSubscriptionRecord(
            id=str(uuid4()),
            workspace_id=workspace_id,
            url=url,
            events_json=events,
            secret_enc=secret_enc,
            active=True,
            created_at=now,
            updated_at=now,
        )
        with Session(self.engine, expire_on_commit=False) as session:
            session.add(record)
            session.commit()
        return self._webhook_response(record)

    def list_webhooks(self, workspace_id: str) -> list[WebhookSubscriptionResponse]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(WebhookSubscriptionRecord)
                .where(WebhookSubscriptionRecord.workspace_id == workspace_id)
                .order_by(WebhookSubscriptionRecord.created_at.desc())
            ).all()
            return [self._webhook_response(record) for record in records]

    def webhook_deliveries(self, workspace_id: str, event: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(WebhookSubscriptionRecord).where(
                    WebhookSubscriptionRecord.workspace_id == workspace_id,
                    WebhookSubscriptionRecord.active.is_(True),
                )
            ).all()
            return [
                {
                    "webhook_id": record.id,
                    "url": record.url,
                    "secret_enc": record.secret_enc,
                }
                for record in records
                if event in (record.events_json or [])
            ]

    def delete_webhook(self, workspace_id: str, webhook_id: str) -> bool:
        with Session(self.engine) as session:
            record = session.scalar(
                select(WebhookSubscriptionRecord).where(
                    WebhookSubscriptionRecord.workspace_id == workspace_id,
                    WebhookSubscriptionRecord.id == webhook_id,
                )
            )
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    @staticmethod
    def _webhook_response(record: WebhookSubscriptionRecord) -> WebhookSubscriptionResponse:
        return WebhookSubscriptionResponse(
            webhook_id=record.id,
            url=record.url,
            events=list(record.events_json or []),
            active=record.active,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

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
