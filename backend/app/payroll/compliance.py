"""Provider-neutral Payroll compliance authority and protected report rendering."""

from __future__ import annotations

import hashlib
import html
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PayrollAuthorizationError, PayrollConflictError, canonical_digest
from .models import (
    PayrollComplianceSchemaRecord,
    PayrollFilingPackageRecord,
    PayrollReportingArtifactRecord,
    PayrollReportingSnapshotRecord,
)
from .permissions import PayrollPermission
from .reporting import FilingConfigurationAuthority
from .reporting_authority import PayrollReportingAuthorityService

COMPLIANCE_AUTHORITY_VERSION = "payroll.compliance-schema.v1"
REPORT_RENDER_VERSION = "payroll.reporting-render.v1"
REPORT_MEDIA_TYPE = "text/html; charset=utf-8"


@dataclass(frozen=True, slots=True)
class DraftComplianceSchema:
    jurisdiction_reference: str
    package_family: str
    tax_year: int
    quarter: int | None
    schema_version: str
    rule_version: str
    required_evidence: tuple[str, ...]
    legal_content_slots: tuple[str, ...]
    effective_start: date
    effective_end: date | None = None

    def __post_init__(self) -> None:
        if not self.jurisdiction_reference or not self.package_family:
            raise ValueError("jurisdiction and package family are required")
        if self.tax_year < 2000 or self.quarter not in {None, 1, 2, 3, 4}:
            raise ValueError("tax year or quarter is invalid")
        if (
            not self.schema_version
            or not self.rule_version
            or not self.required_evidence
        ):
            raise ValueError("schema, rules, and required evidence are required")
        if self.effective_end is not None and self.effective_end < self.effective_start:
            raise ValueError("compliance schema interval is invalid")


@dataclass(frozen=True, slots=True)
class ProtectedReportingArtifact:
    id: UUID
    source_type: str
    source_id: UUID
    digest: str
    media_type: str
    lifecycle: str


class ProtectedPayrollReportStorage:
    """Opaque, tenant-scoped, non-public artifact custody."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise ValueError("protected Payroll artifact root must be absolute")
        self._root = root / "payroll-reporting"

    def put(self, company_id: UUID, reference: str, content: bytes) -> None:
        target = self._target(company_id, reference)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = target.with_suffix(".pending")
        temporary.write_bytes(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)

    def get(self, company_id: UUID, reference: str) -> bytes:
        return self._target(company_id, reference).read_bytes()

    def _target(self, company_id: UUID, reference: str) -> Path:
        if not reference.startswith("pra-") or not reference[4:].isalnum():
            raise PayrollConflictError("invalid protected report reference")
        return self._root / str(company_id) / reference


class PayrollComplianceService:
    def __init__(
        self,
        storage: ProtectedPayrollReportStorage,
        *,
        audit: AuditService = audit_service,
    ) -> None:
        self._storage = storage
        self._audit = audit

    async def create_schema(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        draft: DraftComplianceSchema,
    ) -> PayrollComplianceSchemaRecord:
        self._require(context, PayrollPermission.REPORTING_MANAGE)
        document = {
            "version": COMPLIANCE_AUTHORITY_VERSION,
            "company_id": str(context.company.id),
            "jurisdiction_reference": draft.jurisdiction_reference,
            "package_family": draft.package_family,
            "tax_year": draft.tax_year,
            "quarter": draft.quarter,
            "schema_version": draft.schema_version,
            "rule_version": draft.rule_version,
            "required_evidence": sorted(draft.required_evidence),
            "legal_content_slots": sorted(draft.legal_content_slots),
            "effective_start": draft.effective_start,
            "effective_end": draft.effective_end,
        }
        digest = canonical_digest(document)
        identity = f"payroll-compliance-schema:{digest}"
        existing = await session.scalar(
            select(PayrollComplianceSchemaRecord).where(
                PayrollComplianceSchemaRecord.company_id == context.company.id,
                PayrollComplianceSchemaRecord.schema_identity == identity,
            )
        )
        if existing is not None:
            return existing
        value = PayrollComplianceSchemaRecord(
            company_id=context.company.id,
            jurisdiction_reference=draft.jurisdiction_reference,
            package_family=draft.package_family,
            tax_year=draft.tax_year,
            quarter=draft.quarter,
            schema_version=draft.schema_version,
            rule_version=draft.rule_version,
            required_evidence=sorted(draft.required_evidence),
            legal_content_slots=sorted(draft.legal_content_slots),
            effective_start=draft.effective_start,
            effective_end=draft.effective_end,
            schema_identity=identity,
            schema_digest=digest,
            lifecycle="draft",
            created_by_user_id=context.user.id,
        )
        session.add(value)
        await session.commit()
        return value

    async def approve_schema(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        schema_id: UUID,
    ) -> PayrollComplianceSchemaRecord:
        self._require(context, PayrollPermission.REPORTING_APPROVE)
        value = await session.scalar(
            select(PayrollComplianceSchemaRecord)
            .where(
                PayrollComplianceSchemaRecord.company_id == context.company.id,
                PayrollComplianceSchemaRecord.id == schema_id,
            )
            .with_for_update()
        )
        if value is None or value.lifecycle not in {"draft", "approved"}:
            raise PayrollConflictError("draft compliance schema is required")
        if value.lifecycle == "approved":
            return value
        if value.created_by_user_id == context.user.id:
            raise PayrollAuthorizationError(
                "compliance schema requires independent approval"
            )
        overlaps = await session.scalar(
            select(PayrollComplianceSchemaRecord.id).where(
                PayrollComplianceSchemaRecord.company_id == context.company.id,
                PayrollComplianceSchemaRecord.id != value.id,
                PayrollComplianceSchemaRecord.jurisdiction_reference
                == value.jurisdiction_reference,
                PayrollComplianceSchemaRecord.package_family == value.package_family,
                PayrollComplianceSchemaRecord.tax_year == value.tax_year,
                PayrollComplianceSchemaRecord.quarter.is_(value.quarter)
                if value.quarter is None
                else PayrollComplianceSchemaRecord.quarter == value.quarter,
                PayrollComplianceSchemaRecord.lifecycle == "approved",
            )
        )
        if overlaps is not None:
            raise PayrollConflictError("conflicting approved compliance schema")
        value.lifecycle = "approved"
        value.approved_by_user_id = context.user.id
        value.approved_at = datetime.now(timezone.utc)
        await session.commit()
        return value

    async def render_report(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        report_id: UUID,
    ) -> ProtectedReportingArtifact:
        self._require(context, PayrollPermission.REPORTING_MANAGE)
        report = await session.scalar(
            select(PayrollReportingSnapshotRecord).where(
                PayrollReportingSnapshotRecord.company_id == context.company.id,
                PayrollReportingSnapshotRecord.id == report_id,
            )
        )
        if report is None:
            raise PayrollConflictError("Payroll report was not found")
        data = self._report_document(report)
        return await self._persist_artifact(
            session,
            context=context,
            source_type="report",
            source_id=report.id,
            source_digest=report.report_digest,
            data=data,
        )

    async def prepare_package(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        report_id: UUID,
        schema_id: UUID,
        supersedes_package_id: UUID | None = None,
        amendment_evidence: dict[str, object] | None = None,
    ) -> PayrollFilingPackageRecord:
        self._require(context, PayrollPermission.REPORTING_APPROVE)
        schema = await session.scalar(
            select(PayrollComplianceSchemaRecord).where(
                PayrollComplianceSchemaRecord.company_id == context.company.id,
                PayrollComplianceSchemaRecord.id == schema_id,
                PayrollComplianceSchemaRecord.lifecycle == "approved",
            )
        )
        report = await session.scalar(
            select(PayrollReportingSnapshotRecord).where(
                PayrollReportingSnapshotRecord.company_id == context.company.id,
                PayrollReportingSnapshotRecord.id == report_id,
            )
        )
        if schema is None or report is None:
            raise PayrollConflictError(
                "approved schema and reporting evidence are required"
            )
        predecessor = None
        if supersedes_package_id is not None:
            predecessor = await session.scalar(
                select(PayrollFilingPackageRecord)
                .where(
                    PayrollFilingPackageRecord.company_id == context.company.id,
                    PayrollFilingPackageRecord.id == supersedes_package_id,
                )
                .with_for_update()
            )
            if predecessor is None or predecessor.state != "prepared_not_submitted":
                raise PayrollConflictError(
                    "active predecessor filing package is required"
                )
            if predecessor.reporting_digest == report.report_digest:
                raise PayrollConflictError(
                    "amendment requires changed reporting evidence"
                )
            if not amendment_evidence:
                raise PayrollConflictError("amendment evidence is required")
        authority = FilingConfigurationAuthority(
            schema.schema_identity,
            schema.schema_digest,
            schema.company_id,
            schema.jurisdiction_reference,
            schema.package_family,
            schema.schema_version,
            schema.effective_start,
            schema.effective_end,
            True,
        )
        package = await PayrollReportingAuthorityService().prepare_filing(
            session,
            context=context,
            snapshot_id=report.id,
            authority=authority,
        )
        if package.compliance_schema_id not in {None, schema.id}:
            raise PayrollConflictError("filing package schema replay is contradictory")
        package.compliance_schema_id = schema.id
        if predecessor is not None:
            if package.supersedes_package_id not in {None, predecessor.id}:
                raise PayrollConflictError("filing amendment lineage is contradictory")
            package.supersedes_package_id = predecessor.id
            package.amendment_evidence_digest = canonical_digest(amendment_evidence)
            predecessor.state = "superseded"
        await session.commit()
        return package

    async def render_filing_preview(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        package_id: UUID,
    ) -> ProtectedReportingArtifact:
        self._require(context, PayrollPermission.REPORTING_MANAGE)
        package = await session.scalar(
            select(PayrollFilingPackageRecord).where(
                PayrollFilingPackageRecord.company_id == context.company.id,
                PayrollFilingPackageRecord.id == package_id,
            )
        )
        if package is None or package.state not in {
            "prepared_not_submitted",
            "superseded",
        }:
            raise PayrollConflictError("prepared filing package is required")
        document = (
            "<!doctype html><html><body><h1>Payroll filing-package preview</h1>"
            f"<p>Jurisdiction authority: {html.escape(package.jurisdiction_reference)}</p>"
            f"<p>Package family: {html.escape(package.package_type)}</p>"
            f"<p>Schema: {html.escape(package.schema_version)}</p>"
            f"<p>Status: {html.escape(package.state.replace('_', ' '))}</p>"
            "<p>This is provider-neutral evidence, not an official form and not a filing.</p>"
            f"<footer>Package {package.id}<br>Digest {package.package_digest}</footer>"
            "</body></html>"
        ).encode()
        return await self._persist_artifact(
            session,
            context=context,
            source_type="filing_package",
            source_id=package.id,
            source_digest=package.package_digest,
            data=document,
        )

    async def retrieve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        artifact_id: UUID,
    ) -> tuple[ProtectedReportingArtifact, bytes]:
        self._require(context, PayrollPermission.REPORTING_READ)
        value = await session.scalar(
            select(PayrollReportingArtifactRecord).where(
                PayrollReportingArtifactRecord.company_id == context.company.id,
                PayrollReportingArtifactRecord.id == artifact_id,
            )
        )
        if value is None:
            raise PayrollConflictError("protected Payroll report was not found")
        data = self._storage.get(value.company_id, value.storage_reference)
        self._verify(value, data=data)
        return self._view(value), data

    async def _persist_artifact(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_type: str,
        source_id: UUID,
        source_digest: str,
        data: bytes,
    ) -> ProtectedReportingArtifact:
        digest = hashlib.sha256(data).hexdigest()
        identity = f"payroll-report-artifact:{canonical_digest({'source_digest': source_digest, 'render_version': REPORT_RENDER_VERSION, 'artifact_digest': digest})}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": identity},
        )
        existing = await session.scalar(
            select(PayrollReportingArtifactRecord).where(
                PayrollReportingArtifactRecord.company_id == context.company.id,
                PayrollReportingArtifactRecord.artifact_identity == identity,
            )
        )
        if existing is not None:
            self._verify(
                existing,
                data=self._storage.get(
                    existing.company_id,
                    existing.storage_reference,
                ),
            )
            return self._view(existing)
        reference = f"pra-{digest}"
        self._storage.put(context.company.id, reference, data)
        value = PayrollReportingArtifactRecord(
            company_id=context.company.id,
            source_type=source_type,
            source_id=source_id,
            source_digest=source_digest,
            render_version=REPORT_RENDER_VERSION,
            media_type=REPORT_MEDIA_TYPE,
            storage_reference=reference,
            artifact_identity=identity,
            artifact_digest=digest,
            byte_size=len(data),
            lifecycle="generated",
            created_by_user_id=context.user.id,
        )
        session.add(value)
        await session.flush()
        safe: dict[str, object] = {
            "artifact_id": str(value.id),
            "source_type": source_type,
            "source_id": str(source_id),
            "artifact_digest": digest,
            "lifecycle": value.lifecycle,
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.PAYROLL_REPORT_ARTIFACT_GENERATED,
                entity_type="payroll_reporting_artifact",
                entity_id=value.id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=safe,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action="payroll.reporting.artifact_generated",
                resource_type="payroll_reporting_artifact",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=value.id,
                details=safe,
            ),
        )
        await session.commit()
        return self._view(value)

    @staticmethod
    def _report_document(value: PayrollReportingSnapshotRecord) -> bytes:
        totals = value.totals or {}
        rows = "".join(
            f"<tr><td>{html.escape(key.replace('_', ' ').title())}</td><td>{html.escape(value.currency or '—')} {html.escape(str(amount))}</td></tr>"
            for key, amount in sorted(totals.items())
        )
        return (
            "<!doctype html><html><body><h1>Payroll reporting evidence</h1>"
            f"<p>{html.escape(value.period_kind.replace('_', ' ').title())}: "
            f"{value.period_start} through {value.period_end}</p>"
            f"<p>Authority state: {html.escape(value.state)}</p><table>{rows}</table>"
            "<p>This report is authoritative Payroll evidence only when its state is authoritative. "
            "It is not a tax filing or legal-compliance assertion.</p>"
            f"<footer>Report {value.id}<br>Digest {value.report_digest}</footer>"
            "</body></html>"
        ).encode()

    @staticmethod
    def _view(value: PayrollReportingArtifactRecord) -> ProtectedReportingArtifact:
        return ProtectedReportingArtifact(
            value.id,
            value.source_type,
            value.source_id,
            value.artifact_digest,
            value.media_type,
            value.lifecycle,
        )

    @staticmethod
    def _verify(value: PayrollReportingArtifactRecord, *, data: bytes) -> None:
        if (
            len(data) != value.byte_size
            or hashlib.sha256(data).hexdigest() != value.artifact_digest
        ):
            raise PayrollConflictError("protected Payroll report integrity failed")

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll compliance permission denied")
