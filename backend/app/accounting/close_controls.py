"""Read-only canonical report comparison and period-close control projections."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import (
    AccountingPeriod,
    OpeningControlException,
    OpeningControlPackage,
)
from app.financial_reporting.repository import financial_reporting_repository
from app.platform.permissions.authorization import AuthorizationContext
from app.qbo_source.application_models import QboNativeReviewItem


class ControlModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReportFamily(StrEnum):
    TRIAL_BALANCE = "trial_balance"
    PROFIT_AND_LOSS = "profit_and_loss"
    BALANCE_SHEET = "balance_sheet"
    GENERAL_LEDGER = "general_ledger"
    AR_AGING = "ar_aging"
    AP_AGING = "ap_aging"
    CASH_FLOW = "cash_flow"
    JOB_COSTING = "job_costing"


class ComparisonState(StrEnum):
    COMPARABLE = "COMPARABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ReportLine(ControlModel):
    identity: str = Field(min_length=1, max_length=240)
    label: str = Field(min_length=1, max_length=240)
    amount: Decimal | None = None
    debit: Decimal | None = Field(default=None, ge=0)
    credit: Decimal | None = Field(default=None, ge=0)
    classification: str | None = None
    evidence_reference: str = Field(min_length=1, max_length=500)


class CanonicalReportEvidence(ControlModel):
    authority: str
    available: bool
    family: ReportFamily
    legal_company_identity: str
    company_id: UUID
    branch_id: UUID | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    accounting_basis: str
    start_date: date | None = None
    end_date: date
    cutoff: datetime
    timezone: str
    parameters_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_version: str
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: tuple[str, ...]
    total: Decimal | None = None
    total_debits: Decimal | None = Field(default=None, ge=0)
    total_credits: Decimal | None = Field(default=None, ge=0)
    lines: tuple[ReportLine, ...] = ()
    bucket_semantics_version: str | None = None
    job_cost_semantics_version: str | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> CanonicalReportEvidence:
        if self.cutoff.tzinfo is None:
            raise ValueError("Report cutoff must be timezone-aware")
        if self.start_date is not None and self.start_date > self.end_date:
            raise ValueError("Report start date must not follow end date")
        if self.available and not self.provenance:
            raise ValueError("Available report evidence requires provenance")
        if (
            self.family is ReportFamily.TRIAL_BALANCE
            and self.available
            and (self.total_debits is None or self.total_credits is None)
        ):
            raise ValueError("Trial Balance evidence requires debit and credit totals")
        return self


class ReportLineDifference(ControlModel):
    identity: str
    label: str
    acp_classification: str | None = None
    qbo_classification: str | None = None
    acp_amount: Decimal | None
    qbo_amount: Decimal | None
    difference: Decimal | None
    acp_debit: Decimal | None = None
    acp_credit: Decimal | None = None
    qbo_debit: Decimal | None = None
    qbo_credit: Decimal | None = None
    disposition: str


class ReportComparison(ControlModel):
    family: ReportFamily
    acp_available: bool
    qbo_available: bool
    state: ComparisonState
    non_comparable_reasons: tuple[str, ...]
    start_date: date | None
    end_date: date | None
    cutoff: datetime | None
    basis: str | None
    currency: str | None
    acp_provenance: tuple[str, ...]
    qbo_provenance: tuple[str, ...]
    acp_total: Decimal | None
    qbo_total: Decimal | None
    difference: Decimal | None
    acp_total_debits: Decimal | None
    acp_total_credits: Decimal | None
    qbo_total_debits: Decimal | None
    qbo_total_credits: Decimal | None
    acp_balanced: bool | None
    qbo_balanced: bool | None
    lines: tuple[ReportLineDifference, ...]
    review_state: str
    evidence_digest: str


class AccountantReviewItem(ControlModel):
    source_domain: str
    source_reference: str
    category: str
    state: str
    review_requirement: str
    display_identity: str
    provenance: tuple[str, ...]
    source_lifecycle: str
    action_path: str | None


class AccountantReviewProjection(ControlModel):
    company_id: UUID
    items: tuple[AccountantReviewItem, ...]
    generated_at: datetime


class CloseBlocker(ControlModel):
    code: str
    family: str
    state: str
    explanation: str
    evidence_reference: str | None = None


class PeriodCloseReadiness(ControlModel):
    period_id: UUID
    start_date: date
    end_date: date
    lifecycle_status: str
    accounting_basis: str
    currency: str
    opening_equity_readiness: str
    trial_balance_readiness: str
    ar_readiness: str
    ap_readiness: str
    payroll_readiness: str
    report_comparison_readiness: str
    accountant_review_blocker_count: int
    required_approvals: tuple[str, ...]
    blockers: tuple[CloseBlocker, ...]
    overall_readiness: str
    evidence_digest: str
    generated_at: datetime


class ReportEvidenceProvider(Protocol):
    async def evidence(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        family: ReportFamily,
        period: AccountingPeriod,
    ) -> tuple[CanonicalReportEvidence | None, CanonicalReportEvidence | None]: ...


class UnavailableReportEvidenceProvider:
    async def evidence(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        family: ReportFamily,
        period: AccountingPeriod,
    ) -> tuple[None, None]:
        del session, context, family, period
        return None, None


class PayrollCloseEvidenceProvider(Protocol):
    async def readiness(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period: AccountingPeriod,
    ) -> tuple[str, str | None]: ...


class UnavailablePayrollCloseEvidenceProvider:
    async def readiness(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period: AccountingPeriod,
    ) -> tuple[str, None]:
        del session, context, period
        return "UNAVAILABLE", None


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def compare_reports(
    family: ReportFamily,
    acp: CanonicalReportEvidence | None,
    qbo: CanonicalReportEvidence | None,
) -> ReportComparison:
    reasons: list[str] = []
    if acp is None or not acp.available:
        reasons.append("ACP_REPORT_UNAVAILABLE")
    if qbo is None or not qbo.available:
        reasons.append("QBO_REPORT_UNAVAILABLE")
    if acp and qbo and acp.available and qbo.available:
        dimensions = (
            ("REPORT_FAMILY_MISMATCH", acp.family, qbo.family),
            (
                "LEGAL_COMPANY_MISMATCH",
                acp.legal_company_identity,
                qbo.legal_company_identity,
            ),
            ("COMPANY_SCOPE_MISMATCH", acp.company_id, qbo.company_id),
            ("BRANCH_SCOPE_MISMATCH", acp.branch_id, qbo.branch_id),
            ("CURRENCY_MISMATCH", acp.currency, qbo.currency),
            ("ACCOUNTING_BASIS_MISMATCH", acp.accounting_basis, qbo.accounting_basis),
            ("PERIOD_START_MISMATCH", acp.start_date, qbo.start_date),
            ("PERIOD_END_MISMATCH", acp.end_date, qbo.end_date),
            ("CUTOFF_MISMATCH", acp.cutoff, qbo.cutoff),
            ("TIMEZONE_MISMATCH", acp.timezone, qbo.timezone),
            (
                "REPORT_PARAMETERS_MISMATCH",
                acp.parameters_digest,
                qbo.parameters_digest,
            ),
            ("SOURCE_REPORT_VERSION_MISMATCH", acp.report_version, qbo.report_version),
        )
        reasons.extend(code for code, left, right in dimensions if left != right)
        if family in {ReportFamily.AR_AGING, ReportFamily.AP_AGING} and (
            acp.bucket_semantics_version != qbo.bucket_semantics_version
        ):
            reasons.append("AGING_BUCKET_SEMANTICS_MISMATCH")
        if family is ReportFamily.JOB_COSTING and (
            acp.job_cost_semantics_version != qbo.job_cost_semantics_version
        ):
            reasons.append("JOB_COST_SEMANTICS_MISMATCH")
    state = (
        ComparisonState.UNAVAILABLE
        if any(reason.endswith("UNAVAILABLE") for reason in reasons)
        else ComparisonState.NOT_COMPARABLE
        if reasons
        else ComparisonState.COMPARABLE
    )
    lines: tuple[ReportLineDifference, ...] = ()
    difference: Decimal | None = None
    if state is ComparisonState.COMPARABLE and acp is not None and qbo is not None:
        difference = (
            acp.total - qbo.total
            if acp.total is not None and qbo.total is not None
            else None
        )
        left = {line.identity: line for line in acp.lines}
        right = {line.identity: line for line in qbo.lines}
        rows: list[ReportLineDifference] = []
        for identity in sorted(left.keys() | right.keys()):
            a, q = left.get(identity), right.get(identity)
            amount_difference = (
                a.amount - q.amount
                if a and q and a.amount is not None and q.amount is not None
                else None
            )
            rows.append(
                ReportLineDifference(
                    identity=identity,
                    label=(a or q).label,  # type: ignore[union-attr]
                    acp_classification=a.classification if a else None,
                    qbo_classification=q.classification if q else None,
                    acp_amount=a.amount if a else None,
                    qbo_amount=q.amount if q else None,
                    difference=amount_difference,
                    acp_debit=a.debit if a else None,
                    acp_credit=a.credit if a else None,
                    qbo_debit=q.debit if q else None,
                    qbo_credit=q.credit if q else None,
                    disposition=(
                        "ACP_ONLY"
                        if q is None
                        else "QBO_ONLY"
                        if a is None
                        else "MATCHED"
                        if amount_difference == 0
                        and a.debit == q.debit
                        and a.credit == q.credit
                        else "DIFFERENCE"
                    ),
                )
            )
        lines = tuple(rows)
    payload = {
        "family": family.value,
        "acp_manifest": acp.manifest_digest if acp else None,
        "qbo_manifest": qbo.manifest_digest if qbo else None,
        "state": state.value,
        "reasons": reasons,
    }
    return ReportComparison(
        family=family,
        acp_available=bool(acp and acp.available),
        qbo_available=bool(qbo and qbo.available),
        state=state,
        non_comparable_reasons=tuple(reasons),
        start_date=acp.start_date if acp else qbo.start_date if qbo else None,
        end_date=acp.end_date if acp else qbo.end_date if qbo else None,
        cutoff=acp.cutoff if acp else qbo.cutoff if qbo else None,
        basis=acp.accounting_basis if acp else qbo.accounting_basis if qbo else None,
        currency=acp.currency if acp else qbo.currency if qbo else None,
        acp_provenance=acp.provenance if acp else (),
        qbo_provenance=qbo.provenance if qbo else (),
        acp_total=acp.total if acp else None,
        qbo_total=qbo.total if qbo else None,
        difference=difference,
        acp_total_debits=acp.total_debits if acp else None,
        acp_total_credits=acp.total_credits if acp else None,
        qbo_total_debits=qbo.total_debits if qbo else None,
        qbo_total_credits=qbo.total_credits if qbo else None,
        acp_balanced=(acp.total_debits == acp.total_credits)
        if acp and acp.total_debits is not None and acp.total_credits is not None
        else None,
        qbo_balanced=(qbo.total_debits == qbo.total_credits)
        if qbo and qbo.total_debits is not None and qbo.total_credits is not None
        else None,
        lines=lines,
        review_state="MATCHED"
        if state is ComparisonState.COMPARABLE
        and difference == 0
        and all(row.disposition == "MATCHED" for row in lines)
        else "REVIEW_REQUIRED",
        evidence_digest=_digest(payload),
    )


class AccountingCloseControlService:
    def __init__(
        self,
        provider: ReportEvidenceProvider | None = None,
        payroll_provider: PayrollCloseEvidenceProvider | None = None,
    ) -> None:
        self.provider = provider or UnavailableReportEvidenceProvider()
        self.payroll_provider = (
            payroll_provider or UnavailablePayrollCloseEvidenceProvider()
        )

    async def comparisons(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period: AccountingPeriod,
    ) -> tuple[ReportComparison, ...]:
        results = []
        for family in ReportFamily:
            acp, qbo = await self.provider.evidence(
                session, context=context, family=family, period=period
            )
            results.append(compare_reports(family, acp, qbo))
        return tuple(results)

    async def review_queue(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> AccountantReviewProjection:
        items: list[AccountantReviewItem] = []
        opening = tuple(
            (
                await session.scalars(
                    select(OpeningControlException).where(
                        OpeningControlException.company_id == context.company.id
                    )
                )
            ).all()
        )
        for opening_row in opening:
            items.append(
                AccountantReviewItem(
                    source_domain="opening_controls",
                    source_reference=str(opening_row.id),
                    category=opening_row.control_family,
                    state=opening_row.disposition,
                    review_requirement=opening_row.explanation,
                    display_identity=opening_row.source_identity
                    or opening_row.native_identity
                    or opening_row.exception_identity,
                    provenance=(opening_row.source_digest,),
                    source_lifecycle=opening_row.disposition,
                    action_path=f"/accounting/close?opening={opening_row.package_id}",
                )
            )
        qbo = tuple(
            (
                await session.scalars(
                    select(QboNativeReviewItem).where(
                        QboNativeReviewItem.company_id == context.company.id,
                        QboNativeReviewItem.state == "OPEN",
                    )
                )
            ).all()
        )
        for qbo_row in qbo:
            items.append(
                AccountantReviewItem(
                    source_domain="qbo_application",
                    source_reference=str(qbo_row.id),
                    category=qbo_row.source_family,
                    state=qbo_row.state,
                    review_requirement=qbo_row.exact_conflict,
                    display_identity=qbo_row.reference_number
                    or qbo_row.provider_record_id,
                    provenance=(str(qbo_row.application_record_id),),
                    source_lifecycle=qbo_row.state,
                    action_path="/accounting/qbo-review",
                )
            )
        return AccountantReviewProjection(
            company_id=context.company.id,
            items=tuple(
                sorted(
                    items,
                    key=lambda item: (
                        item.source_domain,
                        item.category,
                        item.source_reference,
                    ),
                )
            ),
            generated_at=datetime.now(timezone.utc),
        )

    async def readiness(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period: AccountingPeriod,
    ) -> PeriodCloseReadiness:
        comparisons = await self.comparisons(session, context=context, period=period)
        queue = await self.review_queue(session, context=context)
        opening = await session.scalar(
            select(OpeningControlPackage)
            .where(
                OpeningControlPackage.company_id == context.company.id,
                OpeningControlPackage.cutoff_at
                <= datetime.combine(
                    period.end_date, datetime.max.time(), tzinfo=timezone.utc
                ),
            )
            .order_by(OpeningControlPackage.cutoff_at.desc())
            .limit(1)
        )
        blockers: list[CloseBlocker] = []
        if opening is None or opening.status not in {"APPROVED", "APPLIED"}:
            blockers.append(
                CloseBlocker(
                    code="OPENING_EQUITY_NOT_APPROVED",
                    family="opening_equity",
                    state="UNAVAILABLE" if opening is None else opening.status,
                    explanation="Approved opening and equity control evidence is required.",
                )
            )
        for result in comparisons:
            if (
                result.state is not ComparisonState.COMPARABLE
                or result.review_state != "MATCHED"
            ):
                blockers.append(
                    CloseBlocker(
                        code=f"{result.family.value.upper()}_COMPARISON_NOT_READY",
                        family=result.family.value,
                        state=result.state.value,
                        explanation="Canonical ACP and sealed QBO report evidence is not matched for this period.",
                        evidence_reference=result.evidence_digest,
                    )
                )
        if queue.items:
            blockers.append(
                CloseBlocker(
                    code="ACCOUNTANT_REVIEW_ITEMS_OPEN",
                    family="accountant_review",
                    state="REVIEW_REQUIRED",
                    explanation=f"{len(queue.items)} governed Accounting review item(s) remain open.",
                )
            )
        payroll_state, payroll_reference = await self.payroll_provider.readiness(
            session, context=context, period=period
        )
        if payroll_state != "READY":
            blockers.append(
                CloseBlocker(
                    code="PAYROLL_PERIOD_CONTROL_NOT_READY",
                    family="payroll",
                    state=payroll_state,
                    explanation="Approved Payroll runs, mappings, posted journals, GL lines, settlement/remittance, and opening/YTD certification must agree for the period.",
                    evidence_reference=payroll_reference,
                )
            )
        report_context = await financial_reporting_repository.context(
            session, context.company.id
        )
        currency = report_context.currency if report_context else "UNAVAILABLE"
        generated_at = datetime.now(timezone.utc)
        digest = _digest(
            {
                "period_id": str(period.id),
                "period_version": period.version,
                "opening": opening.evidence_digest if opening else None,
                "comparisons": [item.evidence_digest for item in comparisons],
                "review": [item.source_reference for item in queue.items],
                "blockers": [item.code for item in blockers],
            }
        )
        return PeriodCloseReadiness(
            period_id=period.id,
            start_date=period.start_date,
            end_date=period.end_date,
            lifecycle_status=period.status,
            accounting_basis="accrual",
            currency=currency,
            opening_equity_readiness="READY"
            if opening and opening.status in {"APPROVED", "APPLIED"}
            else "NOT_READY",
            trial_balance_readiness=next(
                item.review_state
                for item in comparisons
                if item.family is ReportFamily.TRIAL_BALANCE
            ),
            ar_readiness=next(
                item.review_state
                for item in comparisons
                if item.family is ReportFamily.AR_AGING
            ),
            ap_readiness=next(
                item.review_state
                for item in comparisons
                if item.family is ReportFamily.AP_AGING
            ),
            payroll_readiness=payroll_state,
            report_comparison_readiness="READY"
            if all(item.review_state == "MATCHED" for item in comparisons)
            else "NOT_READY",
            accountant_review_blocker_count=len(queue.items),
            required_approvals=("FINANCE_APPROVE",),
            blockers=tuple(blockers),
            overall_readiness="READY" if not blockers else "BLOCKED",
            evidence_digest=digest,
            generated_at=generated_at,
        )


accounting_close_control_service = AccountingCloseControlService()
