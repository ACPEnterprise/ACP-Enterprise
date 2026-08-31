from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.models import AuditRecord
from app.platform.reliability.correlation import current_correlation_id
from app.platform.security.metrics import security_metrics
from app.platform.security.safe_output import (
    sanitize_text,
    validate_no_sensitive_fields,
)


@dataclass(frozen=True)
class AuditEntry:
    action: str
    resource_type: str
    outcome: str = "success"
    actor_user_id: UUID | None = None
    company_id: UUID | None = None
    branch_id: UUID | None = None
    resource_id: UUID | None = None
    reason_code: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    correlation_id: UUID | None = None
    details: dict[str, object] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AuditService:
    @staticmethod
    def stage(session: AsyncSession, entry: AuditEntry) -> AuditRecord:
        AuditService._validate(entry)
        record = AuditRecord(
            action=entry.action,
            outcome=entry.outcome,
            actor_user_id=entry.actor_user_id,
            company_id=entry.company_id,
            branch_id=entry.branch_id,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            reason_code=entry.reason_code,
            ip_address=entry.ip_address,
            user_agent=entry.user_agent,
            correlation_id=entry.correlation_id or current_correlation_id() or uuid4(),
            details=entry.details,
            occurred_at=entry.occurred_at,
        )
        session.add(record)
        security_metrics.record_audit_action(entry.action, entry.outcome)
        return record

    @staticmethod
    def _validate(entry: AuditEntry) -> None:
        if not entry.action.strip() or not entry.resource_type.strip():
            raise ValueError("Audit action and resource type are required")
        if entry.outcome not in {"success", "failure", "denied"}:
            raise ValueError("Audit outcome is invalid")

        for value in (
            entry.action,
            entry.resource_type,
            entry.reason_code,
            entry.user_agent,
        ):
            if value is not None and sanitize_text(value) != value:
                raise ValueError("Sensitive values are prohibited in audit metadata.")

        validate_no_sensitive_fields(entry.details, boundary="audit details")


audit_service = AuditService()
