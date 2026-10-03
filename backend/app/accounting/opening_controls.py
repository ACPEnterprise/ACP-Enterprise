"""QBO opening-state and AR/AP cutoff controls without source mutation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
)
from app.accounting.models import (
    Journal,
    OpeningControlException,
    OpeningControlPackage,
)
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.permissions.authorization import AuthorizationContext


class Disposition(StrEnum):
    MATCHED = "MATCHED"
    SOURCE_ONLY = "SOURCE_ONLY"
    ACP_ONLY = "ACP_ONLY"
    AMOUNT_DIFFERENCE = "AMOUNT_DIFFERENCE"
    DATE_CUTOFF_DIFFERENCE = "DATE_CUTOFF_DIFFERENCE"
    DUPLICATE = "DUPLICATE"
    MISSING_LINK = "MISSING_LINK"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class OpeningControlSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class TrialBalanceLine(OpeningControlSchema):
    source_identity: str = Field(min_length=1, max_length=200)
    account_type: str = Field(min_length=1, max_length=80)
    equity_category: str | None = None
    debit: Decimal = Field(default=Decimal(0), ge=0)
    credit: Decimal = Field(default=Decimal(0), ge=0)
    source_version: str = Field(min_length=1, max_length=80)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def one_sided(self) -> TrialBalanceLine:
        if (self.debit == 0) == (self.credit == 0):
            raise ValueError("Each trial-balance line must contain exactly one side")
        return self


class SubledgerItem(OpeningControlSchema):
    source_identity: str = Field(min_length=1, max_length=200)
    native_identity: str | None = Field(default=None, max_length=200)
    party_identity: str = Field(min_length=1, max_length=200)
    document_identity: str = Field(min_length=1, max_length=200)
    open_amount: Decimal = Field(ge=0)
    as_of: datetime
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    duplicate: bool = False
    evidence_chain: tuple[str, ...] = ()


class OpeningControlPreviewRequest(OpeningControlSchema):
    realm_id: str = Field(min_length=1, max_length=160)
    package_identity: str = Field(min_length=1, max_length=200)
    source_version: str = Field(min_length=1, max_length=80)
    cutoff_at: datetime
    cutoff_timezone: str = Field(min_length=1, max_length=80)
    acquired_at: datetime
    source_as_of: datetime
    source_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trial_balance: tuple[TrialBalanceLine, ...] = Field(min_length=2)
    ar_control_balance: Decimal | None = None
    ap_control_balance: Decimal | None = None
    source_ar: tuple[SubledgerItem, ...] = ()
    native_ar: tuple[SubledgerItem, ...] = ()
    source_ap: tuple[SubledgerItem, ...] = ()
    native_ap: tuple[SubledgerItem, ...] = ()
    opening_equity_review_reference: str | None = None

    @model_validator(mode="after")
    def aware_cutoff(self) -> OpeningControlPreviewRequest:
        dates = (self.cutoff_at, self.acquired_at, self.source_as_of)
        if any(value.tzinfo is None for value in dates):
            raise ValueError("Cutoff and source timestamps must be timezone-aware")
        return self


class ControlExceptionView(OpeningControlSchema):
    exception_identity: str
    control_family: str
    disposition: Disposition
    source_identity: str | None
    native_identity: str | None
    source_amount: Decimal | None
    native_amount: Decimal | None
    source_digest: str
    explanation: str


class OpeningControlPreview(OpeningControlSchema):
    package_identity: str
    cutoff_at: datetime
    total_debits: Decimal
    total_credits: Decimal
    balanced: bool
    ar_control_balance: Decimal | None
    ar_subledger_balance: Decimal | None
    ar_difference: Decimal | None
    ap_control_balance: Decimal | None
    ap_subledger_balance: Decimal | None
    ap_difference: Decimal | None
    balance_sheet_equation_supported: bool
    unexplained_equity: bool
    status: str
    evidence_digest: str
    exceptions: tuple[ControlExceptionView, ...]


class OpeningControlTransition(OpeningControlSchema):
    expected_version: int = Field(ge=1)
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class OpeningControlSubmit(OpeningControlSchema):
    preview: OpeningControlPreviewRequest
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class SealedOpeningPackageSelection(OpeningControlSchema):
    """An operator selects sealed custody; the server constructs accounting facts."""

    package_identity: str = Field(min_length=1, max_length=200)


class OpeningControlPage(OpeningControlSchema):
    package_id: UUID
    items: tuple[Mapping[str, object], ...]
    offset: int
    limit: int
    total: int


class OpeningControlApply(OpeningControlTransition):
    journal_id: UUID


class OpeningControlResponse(OpeningControlSchema):
    id: UUID
    company_id: UUID
    realm_id: str
    package_identity: str
    cutoff_at: datetime
    status: str
    evidence_digest: str
    total_debits: Decimal
    total_credits: Decimal
    ar_control_balance: Decimal | None
    ar_subledger_balance: Decimal | None
    ap_control_balance: Decimal | None
    ap_subledger_balance: Decimal | None
    version: int
    approved_by_user_id: UUID | None
    applied_journal_id: UUID | None


class OpeningControlDetail(OpeningControlSchema):
    package: OpeningControlResponse
    trial_balance: tuple[TrialBalanceLine, ...]
    total_debits: Decimal
    total_credits: Decimal
    difference: Decimal
    equity_categories: tuple[str, ...]
    ar_difference: Decimal | None
    ap_difference: Decimal | None
    source_as_of: datetime
    cutoff_at: datetime
    lifecycle: tuple[Mapping[str, object], ...]


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _subledger(
    family: str,
    cutoff: datetime,
    source: tuple[SubledgerItem, ...],
    native: tuple[SubledgerItem, ...],
) -> tuple[Decimal, tuple[ControlExceptionView, ...]]:
    exceptions: list[ControlExceptionView] = []
    native_by_link = {item.source_identity: item for item in native}
    source_ids: set[str] = set()
    for item in source:
        disposition = Disposition.MATCHED
        matched = native_by_link.get(item.source_identity)
        explanation = "Source and native open obligation agree at cutoff."
        if item.duplicate or item.source_identity in source_ids:
            disposition, explanation = (
                Disposition.DUPLICATE,
                "Duplicate source identity.",
            )
        elif item.as_of != cutoff:
            disposition, explanation = (
                Disposition.DATE_CUTOFF_DIFFERENCE,
                "Evidence cutoff differs from the opening cutoff.",
            )
        elif matched is None:
            disposition, explanation = (
                Disposition.SOURCE_ONLY,
                "No native successor link.",
            )
        elif matched.as_of != cutoff:
            disposition, explanation = (
                Disposition.DATE_CUTOFF_DIFFERENCE,
                "Native evidence is not authoritative at the same cutoff.",
            )
        elif matched.open_amount != item.open_amount:
            disposition, explanation = (
                Disposition.AMOUNT_DIFFERENCE,
                "Source and native open amounts differ.",
            )
        source_ids.add(item.source_identity)
        if disposition is not Disposition.MATCHED:
            exceptions.append(
                ControlExceptionView(
                    exception_identity=_digest(
                        [family, item.source_identity, disposition.value]
                    ),
                    control_family=family,
                    disposition=disposition,
                    source_identity=item.source_identity,
                    native_identity=matched.native_identity if matched else None,
                    source_amount=item.open_amount,
                    native_amount=matched.open_amount if matched else None,
                    source_digest=item.source_digest,
                    explanation=explanation,
                )
            )
    for item in native:
        if item.source_identity not in source_ids:
            exceptions.append(
                ControlExceptionView(
                    exception_identity=_digest(
                        [family, item.native_identity, "ACP_ONLY"]
                    ),
                    control_family=family,
                    disposition=Disposition.ACP_ONLY,
                    source_identity=None,
                    native_identity=item.native_identity,
                    source_amount=None,
                    native_amount=item.open_amount,
                    source_digest=item.source_digest,
                    explanation="Native open obligation has no source cutoff item.",
                )
            )
    return sum((item.open_amount for item in source), Decimal(0)), tuple(exceptions)


def preview_opening_controls(
    request: OpeningControlPreviewRequest,
) -> OpeningControlPreview:
    debits = sum((line.debit for line in request.trial_balance), Decimal(0))
    credits = sum((line.credit for line in request.trial_balance), Decimal(0))
    ar_total, ar_exceptions = _subledger(
        "AR", request.cutoff_at, request.source_ar, request.native_ar
    )
    ap_total, ap_exceptions = _subledger(
        "AP", request.cutoff_at, request.source_ap, request.native_ap
    )
    exceptions = list(ar_exceptions + ap_exceptions)
    if request.ar_control_balance is None or request.ar_control_balance != ar_total:
        exceptions.append(
            ControlExceptionView(
                exception_identity=_digest(["AR", "control", request.package_identity]),
                control_family="AR",
                disposition=Disposition.REVIEW_REQUIRED,
                source_identity="ar-control",
                native_identity=None,
                source_amount=request.ar_control_balance,
                native_amount=ar_total,
                source_digest=request.source_manifest_digest,
                explanation="AR subledger does not tie to the cutoff control balance.",
            )
        )
    if request.ap_control_balance is None or request.ap_control_balance != ap_total:
        exceptions.append(
            ControlExceptionView(
                exception_identity=_digest(["AP", "control", request.package_identity]),
                control_family="AP",
                disposition=Disposition.REVIEW_REQUIRED,
                source_identity="ap-control",
                native_identity=None,
                source_amount=request.ap_control_balance,
                native_amount=ap_total,
                source_digest=request.source_manifest_digest,
                explanation="AP subledger does not tie to the cutoff control balance.",
            )
        )
    opening_equity = any(
        line.equity_category == "opening_equity" and (line.debit or line.credit)
        for line in request.trial_balance
    )
    unexplained_equity = opening_equity and not request.opening_equity_review_reference
    if debits != credits or unexplained_equity:
        exceptions.append(
            ControlExceptionView(
                exception_identity=_digest(["OPENING", request.package_identity]),
                control_family="OPENING_EQUITY",
                disposition=Disposition.REVIEW_REQUIRED,
                source_identity=None,
                native_identity=None,
                source_amount=debits - credits,
                native_amount=None,
                source_digest=request.source_manifest_digest,
                explanation=(
                    "Opening Balance Equity requires explicit accountant review."
                    if unexplained_equity
                    else "Trial balance debits and credits are unequal; no plug is permitted."
                ),
            )
        )
    snapshot = request.model_dump(mode="json")
    evidence_digest = _digest(snapshot)
    ready = not exceptions and debits == credits
    return OpeningControlPreview(
        package_identity=request.package_identity,
        cutoff_at=request.cutoff_at,
        total_debits=debits,
        total_credits=credits,
        balanced=debits == credits,
        ar_control_balance=request.ar_control_balance,
        ar_subledger_balance=ar_total,
        ar_difference=(
            request.ar_control_balance - ar_total
            if request.ar_control_balance is not None
            else None
        ),
        ap_control_balance=request.ap_control_balance,
        ap_subledger_balance=ap_total,
        ap_difference=(
            request.ap_control_balance - ap_total
            if request.ap_control_balance is not None
            else None
        ),
        balance_sheet_equation_supported=debits == credits,
        unexplained_equity=unexplained_equity,
        status="READY_FOR_APPROVAL" if ready else "REVIEW_REQUIRED",
        evidence_digest=evidence_digest,
        exceptions=tuple(exceptions),
    )


class OpeningControlService:
    async def submit(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request: OpeningControlPreviewRequest,
        expected_digest: str,
    ) -> OpeningControlPackage:
        preview = preview_opening_controls(request)
        if preview.evidence_digest != expected_digest:
            raise AccountingConflict(
                "Opening preview evidence changed before submission"
            )
        existing = await session.scalar(
            select(OpeningControlPackage).where(
                OpeningControlPackage.company_id == context.company.id,
                OpeningControlPackage.realm_id == request.realm_id,
                OpeningControlPackage.package_identity == request.package_identity,
            )
        )
        if existing is not None:
            if existing.evidence_digest == expected_digest:
                return existing
            raise AccountingConflict(
                "Opening package replay conflicts with prior evidence"
            )
        row = OpeningControlPackage(
            company_id=context.company.id,
            realm_id=request.realm_id,
            package_identity=request.package_identity,
            source_version=request.source_version,
            cutoff_at=request.cutoff_at,
            cutoff_timezone=request.cutoff_timezone,
            acquired_at=request.acquired_at,
            source_as_of=request.source_as_of,
            source_manifest_digest=request.source_manifest_digest,
            evidence_digest=preview.evidence_digest,
            status=preview.status,
            total_debits=preview.total_debits,
            total_credits=preview.total_credits,
            ar_control_balance=preview.ar_control_balance,
            ar_subledger_balance=preview.ar_subledger_balance,
            ap_control_balance=preview.ap_control_balance,
            ap_subledger_balance=preview.ap_subledger_balance,
            evidence_snapshot=request.model_dump(mode="json"),
            prepared_by_user_id=context.user.id,
        )
        session.add(row)
        await session.flush()
        for item in preview.exceptions:
            session.add(
                OpeningControlException(
                    company_id=context.company.id,
                    package_id=row.id,
                    **item.model_dump(),
                )
            )
        self._audit(session, context, "accounting.opening_controls.submitted", row.id)
        return row

    async def approve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        package_id: UUID,
        transition: OpeningControlTransition,
    ) -> OpeningControlPackage:
        row = await self._locked(session, context.company.id, package_id)
        if row.status == "APPROVED":
            return row
        if row.status != "READY_FOR_APPROVAL":
            raise AccountingConflict("Opening control exceptions require resolution")
        if (
            row.version != transition.expected_version
            or row.evidence_digest != transition.evidence_digest
        ):
            raise AccountingConflict("Opening control evidence is stale")
        if row.prepared_by_user_id == context.user.id:
            raise AccountingConflict("Opening preparer and approver must differ")
        row.status = "APPROVED"
        row.approved_by_user_id = context.user.id
        row.approved_at = datetime.now(timezone.utc)
        row.version += 1
        await session.flush()
        self._audit(session, context, "accounting.opening_controls.approved", row.id)
        return row

    async def mark_applied(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        package_id: UUID,
        journal_id: UUID,
        transition: OpeningControlTransition,
    ) -> OpeningControlPackage:
        row = await self._locked(session, context.company.id, package_id)
        if row.status == "APPLIED":
            return row
        if row.status != "APPROVED" or row.version != transition.expected_version:
            raise AccountingConflict("Approved current opening controls are required")
        if row.evidence_digest != transition.evidence_digest:
            raise AccountingConflict("Opening application digest differs from approval")
        journal = await session.scalar(
            select(Journal).where(
                Journal.company_id == context.company.id,
                Journal.id == journal_id,
                Journal.journal_type == "opening",
                Journal.status == "posted",
                Journal.source_digest == row.evidence_digest,
            )
        )
        if journal is None:
            raise AccountingNotFound("Governed posted opening journal was not found")
        row.status = "APPLIED"
        row.applied_journal_id = journal.id
        row.applied_at = datetime.now(timezone.utc)
        row.version += 1
        await session.flush()
        self._audit(session, context, "accounting.opening_controls.applied", row.id)
        return row

    @staticmethod
    async def _locked(
        session: AsyncSession, company_id: UUID, package_id: UUID
    ) -> OpeningControlPackage:
        row = await session.scalar(
            select(OpeningControlPackage)
            .where(
                OpeningControlPackage.company_id == company_id,
                OpeningControlPackage.id == package_id,
            )
            .with_for_update()
        )
        if row is None:
            raise AccountingNotFound("Opening control package was not found")
        return row

    @staticmethod
    def _audit(
        session: AsyncSession,
        context: AuthorizationContext,
        action: str,
        resource_id: UUID,
    ) -> None:
        AuditService.stage(
            session,
            AuditEntry(
                action=action,
                outcome="success",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=context.active_branch.id if context.active_branch else None,
                resource_type="opening_control_package",
                resource_id=resource_id,
            ),
        )


opening_control_service = OpeningControlService()
