"""Protected rendering, retrieval, and link-delivery for pay statements."""

from __future__ import annotations

import hashlib
import html
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.notifications.repository import NotificationOutboxRepository
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import (
    PayrollAuthorizationError,
    PayrollConflictError,
    canonical_digest,
)
from .models import (
    PayrollPayStatementArtifactRecord,
    PayrollPayStatementDeliveryRecord,
    PayrollPayStatementRecord,
)
from .permissions import PayrollPermission

RENDER_CONTRACT_VERSION = "payroll.pay-statement-render.v1"
TEMPLATE_VERSION = "acp-neutral-pay-statement.v1"
RENDERER_VERSION = "acp-deterministic-html.v1"
MEDIA_TYPE = "text/html; charset=utf-8"


@dataclass(frozen=True)
class ProtectedArtifact:
    id: UUID
    statement_id: UUID
    media_type: str
    digest: str
    byte_size: int
    lifecycle: str


class ProtectedStatementStorage:
    """Non-public filesystem custody using opaque references and mode 0600."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise ValueError("protected statement storage root must be absolute")
        self._root = root

    def put(
        self, company_id: UUID, employee_id: UUID, reference: str, content: bytes
    ) -> None:
        target = self._target(company_id, employee_id, reference)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = target.with_suffix(".pending")
        temporary.write_bytes(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)

    def get(self, company_id: UUID, employee_id: UUID, reference: str) -> bytes:
        return self._target(company_id, employee_id, reference).read_bytes()

    def _target(self, company_id: UUID, employee_id: UUID, reference: str) -> Path:
        if not reference.startswith("psa-") or not reference[4:].isalnum():
            raise PayrollConflictError("invalid protected artifact reference")
        return self._root / str(company_id) / str(employee_id) / reference


class DeterministicPayStatementRenderer:
    def render(
        self,
        statement: PayrollPayStatementRecord,
        *,
        company_name: str,
        employee_name: str,
    ) -> bytes:
        if statement.lifecycle not in {"issued", "superseded"}:
            raise PayrollConflictError("only issued statement evidence may be rendered")
        content = statement.content
        raw_earnings = content.get("earnings", [])
        earnings = raw_earnings if isinstance(raw_earnings, list) else []
        rows = "".join(
            f"<tr><td>{html.escape(str(item.get('category', item.get('kind', 'Earnings'))))}</td>"
            f"<td>{html.escape(str(item.get('amount', '—')))}</td></tr>"
            for item in earnings
            if isinstance(item, dict)
        )
        correction = (
            "Corrected statement"
            if statement.supersedes_statement_id
            else "Original statement"
        )
        ytd = content.get("ytd")
        ytd_rows = (
            "".join(
                f"<tr><td>{html.escape(str(key).replace('_', ' ').title())}</td><td>{html.escape(statement.currency)} {html.escape(str(value))}</td></tr>"
                for key, value in ytd.items()
            )
            if statement.ytd_status == "authoritative" and isinstance(ytd, dict)
            else ""
        )
        ytd_section = (
            f"<h2>Year to date</h2><table><tbody>{ytd_rows}</tbody></table>"
            if ytd_rows
            else '<p class="notice">Year-to-date totals are unavailable because complete authoritative history is not available.</p>'
        )
        document = f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Pay statement {statement.id}</title><style>body{{font:16px system-ui;color:#17212b;max-width:760px;margin:32px auto}}h1{{border-bottom:3px solid #285f78;padding-bottom:12px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #ccd6dc;text-align:left}}.total{{font-weight:700}}.notice{{background:#f2f6f8;padding:12px}}</style></head><body><h1>Pay Statement</h1><p><strong>{html.escape(company_name)}</strong><br>{html.escape(employee_name)}</p><p>Pay period: {html.escape(str(content["period_start"]))} through {html.escape(str(content["period_end"]))}<br>Statement version: {statement.statement_version} · {correction}</p><h2>Earnings</h2><table><tbody>{rows}<tr class=\"total\"><td>Gross pay</td><td>{html.escape(statement.currency)} {html.escape(str(content["gross_pay"]))}</td></tr></tbody></table><h2>Employee taxes and deductions</h2><table><tbody><tr><td>Employee taxes</td><td>{html.escape(statement.currency)} {html.escape(str(content["employee_taxes"]))}</td></tr><tr><td>Employee deductions</td><td>{html.escape(statement.currency)} {html.escape(str(content["employee_deductions"]))}</td></tr><tr class=\"total\"><td>Net pay</td><td>{html.escape(statement.currency)} {html.escape(str(content["net_pay"]))}</td></tr></tbody></table><p>Payment method: {html.escape(str(content.get("payment_method") or "Not available"))}<br>Payment status: {html.escape(statement.payment_status.replace("_", " ").title())}</p>{ytd_section}<p class=\"notice\">Jurisdiction-specific legal content is not configured.</p><footer>Statement ID: {statement.id}<br>Statement digest: {statement.statement_digest}</footer></body></html>"""
        return document.encode("utf-8")


class PayrollPayStatementExperienceService:
    def __init__(
        self, storage: ProtectedStatementStorage, *, audit: AuditService = audit_service
    ) -> None:
        self._storage, self._audit = storage, audit
        self._renderer = DeterministicPayStatementRenderer()

    async def render(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        statement_id: UUID,
    ) -> ProtectedArtifact:
        self._require(context, PayrollPermission.STATEMENT_MANAGE)
        statement = await self._statement(session, context.company.id, statement_id)
        employee = await session.scalar(
            select(Employee).where(
                Employee.company_id == context.company.id,
                Employee.id == statement.employee_id,
            )
        )
        company = await session.scalar(
            select(Company).where(Company.id == context.company.id)
        )
        if (
            employee is None
            or company is None
            or canonical_digest(self._economic(statement)) != statement.statement_digest
        ):
            raise PayrollConflictError("statement evidence does not verify")
        data = self._renderer.render(
            statement, company_name=company.name, employee_name=employee.display_name
        )
        digest = hashlib.sha256(data).hexdigest()
        identity = f"paystatement-artifact:{canonical_digest({'statement_digest': statement.statement_digest, 'render_contract': RENDER_CONTRACT_VERSION, 'template': TEMPLATE_VERSION, 'renderer': RENDERER_VERSION, 'artifact_digest': digest})}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": identity},
        )
        existing = await session.scalar(
            select(PayrollPayStatementArtifactRecord).where(
                PayrollPayStatementArtifactRecord.company_id == context.company.id,
                PayrollPayStatementArtifactRecord.artifact_identity == identity,
            )
        )
        if existing is not None:
            self._verify(
                existing,
                data=self._storage.get(
                    existing.company_id,
                    existing.employee_id,
                    existing.storage_reference,
                ),
            )
            return self._view(existing)
        reference = f"psa-{digest}"
        self._storage.put(statement.company_id, statement.employee_id, reference, data)
        value = PayrollPayStatementArtifactRecord(
            company_id=context.company.id,
            employee_id=statement.employee_id,
            statement_id=statement.id,
            statement_digest=statement.statement_digest,
            render_contract_version=RENDER_CONTRACT_VERSION,
            template_version=TEMPLATE_VERSION,
            renderer_version=RENDERER_VERSION,
            media_type=MEDIA_TYPE,
            artifact_digest=digest,
            artifact_identity=identity,
            storage_reference=reference,
            byte_size=len(data),
            lifecycle="generated",
            retention_state="preserve",
            created_by_user_id=context.user.id,
        )
        session.add(value)
        await session.flush()
        self._stage(
            session,
            context,
            statement,
            EventType.PAYROLL_STATEMENT_ARTIFACT_GENERATED,
            "artifact_generated",
            artifact_id=value.id,
        )
        await session.commit()
        return self._view(value)

    async def own_artifact(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        statement_id: UUID,
    ) -> tuple[ProtectedArtifact, bytes]:
        self._require(context, PayrollPermission.STATEMENT_OWN_READ)
        employee = await session.scalar(
            select(Employee).where(
                Employee.company_id == context.company.id,
                Employee.membership_id == context.membership.id,
                Employee.status == "active",
            )
        )
        statement = await self._statement(session, context.company.id, statement_id)
        if (
            employee is None
            or statement.employee_id != employee.id
            or statement.lifecycle not in {"issued", "superseded"}
        ):
            raise PayrollAuthorizationError("statement artifact access denied")
        artifact = await self._artifact(session, context.company.id, statement.id)
        data = self._storage.get(
            artifact.company_id, artifact.employee_id, artifact.storage_reference
        )
        self._verify(artifact, data=data)
        self._stage(
            session,
            context,
            statement,
            EventType.PAYROLL_STATEMENT_ARTIFACT_ACCESSED,
            "artifact_accessed",
            artifact_id=artifact.id,
        )
        await session.commit()
        return self._view(artifact), data

    async def administrative_artifact(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        statement_id: UUID,
    ) -> tuple[ProtectedArtifact, bytes]:
        self._require(context, PayrollPermission.STATEMENT_READ)
        statement = await self._statement(session, context.company.id, statement_id)
        artifact = await self._artifact(session, context.company.id, statement.id)
        data = self._storage.get(
            artifact.company_id, artifact.employee_id, artifact.storage_reference
        )
        self._verify(artifact, data=data)
        self._stage(
            session,
            context,
            statement,
            EventType.PAYROLL_STATEMENT_ARTIFACT_ACCESSED,
            "administrative_artifact_accessed",
            artifact_id=artifact.id,
        )
        await session.commit()
        return self._view(artifact), data

    async def prepare_delivery(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        statement_id: UUID,
        channel: str,
        recipient_reference: str,
        expires_at: datetime | None = None,
    ) -> PayrollPayStatementDeliveryRecord:
        self._require(context, PayrollPermission.STATEMENT_MANAGE)
        if channel not in {
            "authenticated_web",
            "authenticated_app",
            "email_link",
            "push_link",
        }:
            raise PayrollConflictError("unsupported statement delivery channel")
        statement = await self._statement(session, context.company.id, statement_id)
        if statement.lifecycle != "issued":
            raise PayrollConflictError("issued statement is required")
        link = f"/employee/pay-statements/{statement.id}"
        facts = {
            "statement_id": str(statement.id),
            "statement_digest": statement.statement_digest,
            "employee_id": str(statement.employee_id),
            "channel": channel,
            "link_target": link,
            "provider": "notification-outbox",
            "provider_version": "v1",
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
        digest = canonical_digest(facts)
        identity = f"paystatement-delivery:{digest}"
        existing = await session.scalar(
            select(PayrollPayStatementDeliveryRecord).where(
                PayrollPayStatementDeliveryRecord.company_id == context.company.id,
                PayrollPayStatementDeliveryRecord.delivery_identity == identity,
            )
        )
        if existing is not None:
            return existing
        value = PayrollPayStatementDeliveryRecord(
            company_id=context.company.id,
            employee_id=statement.employee_id,
            statement_id=statement.id,
            statement_digest=statement.statement_digest,
            channel=channel,
            link_target=link,
            provider_identity="notification-outbox",
            provider_version="v1",
            delivery_identity=identity,
            delivery_digest=digest,
            lifecycle="prepared",
            expires_at=expires_at,
            created_by_user_id=context.user.id,
        )
        session.add(value)
        await session.flush()
        await NotificationOutboxRepository.enqueue(
            session,
            notification_type="payroll.pay_statement_available",
            template_identifier="payroll-pay-statement-link-v1",
            recipient=recipient_reference,
            recipient_reference=recipient_reference,
            payload={
                "message": "A new pay statement is available.",
                "link": link,
                "pay_period_id": str(statement.pay_period_id),
            },
            correlation_id=value.id,
            idempotency_key=identity,
            scheduled_at=datetime.now(timezone.utc),
            now=datetime.now(timezone.utc),
            company_id=context.company.id,
            channel=channel,
            actor_user_id=context.user.id,
        )
        self._stage(
            session,
            context,
            statement,
            EventType.PAYROLL_STATEMENT_DELIVERY_PREPARED,
            "delivery_prepared",
            delivery_id=value.id,
        )
        await session.commit()
        return value

    @staticmethod
    def _economic(v: PayrollPayStatementRecord) -> dict[str, object]:
        value: dict[str, object] = {
            "company_id": str(v.company_id),
            "employee_id": str(v.employee_id),
            "pay_period_id": str(v.pay_period_id),
            "run_id": str(v.run_id),
            "run_digest": v.run_digest,
            "gross_result_id": str(v.gross_result_id),
            "gross_digest": v.gross_result_digest,
            "tax_result_id": str(v.tax_result_id),
            "tax_digest": v.tax_result_digest,
            "adjustment_result_id": str(v.adjustment_result_id)
            if v.adjustment_result_id
            else None,
            "adjustment_digest": v.adjustment_digest,
            "supersedes_statement_id": str(v.supersedes_statement_id)
            if v.supersedes_statement_id
            else None,
            "currency": v.currency,
            "payment_status": v.payment_status,
            "payment_evidence_digest": v.payment_evidence_digest,
            "content": v.content,
            "ytd_status": v.ytd_status,
            "definition_version": v.definition_version,
        }
        if v.reporting_snapshot_id is not None:
            value["reporting_snapshot_id"] = str(v.reporting_snapshot_id)
            value["reporting_digest"] = v.reporting_digest
        return value

    async def _statement(
        self, session: AsyncSession, company_id: UUID, statement_id: UUID
    ) -> PayrollPayStatementRecord:
        value = await session.scalar(
            select(PayrollPayStatementRecord).where(
                PayrollPayStatementRecord.company_id == company_id,
                PayrollPayStatementRecord.id == statement_id,
            )
        )
        if value is None:
            raise PayrollConflictError("pay statement was not found")
        return value

    async def _artifact(
        self, session: AsyncSession, company_id: UUID, statement_id: UUID
    ) -> PayrollPayStatementArtifactRecord:
        value = await session.scalar(
            select(PayrollPayStatementArtifactRecord)
            .where(
                PayrollPayStatementArtifactRecord.company_id == company_id,
                PayrollPayStatementArtifactRecord.statement_id == statement_id,
                PayrollPayStatementArtifactRecord.lifecycle.in_(
                    ("generated", "retained")
                ),
            )
            .order_by(PayrollPayStatementArtifactRecord.created_at.desc())
        )
        if value is None:
            raise PayrollConflictError("pay statement artifact is unavailable")
        return value

    @staticmethod
    def _verify(value: PayrollPayStatementArtifactRecord, *, data: bytes) -> None:
        if (
            hashlib.sha256(data).hexdigest() != value.artifact_digest
            or len(data) != value.byte_size
        ):
            raise PayrollConflictError(
                "protected pay statement artifact failed verification"
            )

    @staticmethod
    def _view(v: PayrollPayStatementArtifactRecord) -> ProtectedArtifact:
        return ProtectedArtifact(
            v.id,
            v.statement_id,
            v.media_type,
            v.artifact_digest,
            v.byte_size,
            v.lifecycle,
        )

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("pay statement permission denied")

    def _stage(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        statement: PayrollPayStatementRecord,
        event: EventType,
        action: str,
        **references: object,
    ) -> None:
        details: dict[str, object] = {
            "statement_id": str(statement.id),
            "statement_digest": statement.statement_digest,
            "employee_id": str(statement.employee_id),
            "pay_period_id": str(statement.pay_period_id),
            **{key: str(value) for key, value in references.items()},
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event,
                entity_type="payroll_pay_statement",
                entity_id=statement.id,
                company_id=statement.company_id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action=f"payroll.pay_statement.{action}",
                resource_type="payroll_pay_statement",
                actor_user_id=context.user.id,
                company_id=statement.company_id,
                resource_id=statement.id,
                details=details,
            ),
        )
