"""Read-only Payroll-to-Accounting control and sealed opening evidence contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import Journal, JournalLine
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import PayrollAuthorizationError, PayrollConflictError
from .models import (
    PayrollAccountingConsumptionRecord,
    PayrollAccountingMappingVersion,
    PayrollRunRecord,
)
from .permissions import PayrollPermission


class PayrollControlDisposition(StrEnum):
    MATCHED = "MATCHED"
    SOURCE_ONLY = "SOURCE_ONLY"
    ACP_ONLY = "ACP_ONLY"
    AMOUNT_DIFFERENCE = "AMOUNT_DIFFERENCE"
    DATE_CUTOFF_DIFFERENCE = "DATE_CUTOFF_DIFFERENCE"
    MISSING_LINK = "MISSING_LINK"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class PayrollControlSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PayrollControlAmount(PayrollControlSchema):
    category: str = Field(min_length=1, max_length=80)
    payroll_amount: Decimal | None
    general_ledger_amount: Decimal | None
    payroll_source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    ledger_source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    payroll_cutoff: datetime | None
    ledger_cutoff: datetime | None
    source_linked: bool = True


class PayrollAccountingControlRequest(PayrollControlSchema):
    cutoff_at: datetime
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amounts: tuple[PayrollControlAmount, ...]

    @model_validator(mode="after")
    def validate_cutoff(self) -> PayrollAccountingControlRequest:
        if self.cutoff_at.tzinfo is None:
            raise ValueError("Payroll Accounting cutoff must be timezone-aware")
        if len({item.category for item in self.amounts}) != len(self.amounts):
            raise ValueError("Payroll Accounting categories must be unique")
        return self


class PayrollControlFinding(PayrollControlSchema):
    category: str
    disposition: PayrollControlDisposition
    payroll_amount: Decimal | None
    general_ledger_amount: Decimal | None
    difference: Decimal | None
    explanation: str


class PayrollAccountingControlProjection(PayrollControlSchema):
    cutoff_at: datetime
    currency: str
    status: str
    findings: tuple[PayrollControlFinding, ...]
    evidence_digest: str


class PayrollOpeningEmployeeEvidence(PayrollControlSchema):
    employee_id: str = Field(min_length=1, max_length=200)
    gross_ytd: Decimal
    tax_ytd: Decimal
    deductions_ytd: Decimal
    net_ytd: Decimal
    employer_liability_ytd: Decimal
    prior_settlement_total: Decimal
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PayrollOpeningEvidence(PayrollControlSchema):
    package_identity: str = Field(min_length=1, max_length=200)
    cutoff_at: datetime
    source: str = Field(min_length=1, max_length=120)
    accountant_certification_reference: str = Field(min_length=1, max_length=200)
    employees: tuple[PayrollOpeningEmployeeEvidence, ...]
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify(self) -> PayrollOpeningEvidence:
        if self.cutoff_at.tzinfo is None:
            raise ValueError("Payroll opening cutoff must be timezone-aware")
        if len({item.employee_id for item in self.employees}) != len(self.employees):
            raise ValueError("Payroll opening employee identities must be unique")
        payload = self.model_dump(mode="json", exclude={"evidence_digest"})
        digest = _digest(payload)
        if digest != self.evidence_digest:
            raise ValueError("Payroll opening evidence digest conflicts")
        return self


def reconcile_payroll_accounting(
    request: PayrollAccountingControlRequest,
) -> PayrollAccountingControlProjection:
    findings: list[PayrollControlFinding] = []
    for item in sorted(request.amounts, key=lambda value: value.category):
        if item.payroll_amount is None and item.general_ledger_amount is None:
            disposition = PayrollControlDisposition.REVIEW_REQUIRED
            explanation = "Neither Payroll nor Accounting has evidence at cutoff."
            difference = None
        elif item.payroll_amount is None:
            disposition = PayrollControlDisposition.ACP_ONLY
            explanation = "Accounting has a balance without linked Payroll evidence."
            difference = None
        elif item.general_ledger_amount is None:
            disposition = PayrollControlDisposition.SOURCE_ONLY
            explanation = "Payroll has evidence without a linked GL balance."
            difference = None
        elif (
            item.payroll_cutoff != request.cutoff_at
            or item.ledger_cutoff != request.cutoff_at
        ):
            disposition = PayrollControlDisposition.DATE_CUTOFF_DIFFERENCE
            explanation = (
                "Payroll and Accounting evidence are not at the identical cutoff."
            )
            difference = item.general_ledger_amount - item.payroll_amount
        elif not item.source_linked:
            disposition = PayrollControlDisposition.MISSING_LINK
            explanation = "The Payroll fact is not linked to the Accounting balance."
            difference = item.general_ledger_amount - item.payroll_amount
        elif item.payroll_amount != item.general_ledger_amount:
            disposition = PayrollControlDisposition.AMOUNT_DIFFERENCE
            explanation = "Payroll subledger and GL control balance differ."
            difference = item.general_ledger_amount - item.payroll_amount
        else:
            disposition = PayrollControlDisposition.MATCHED
            explanation = "Payroll subledger and GL control balance agree at cutoff."
            difference = Decimal(0)
        findings.append(
            PayrollControlFinding(
                category=item.category,
                disposition=disposition,
                payroll_amount=item.payroll_amount,
                general_ledger_amount=item.general_ledger_amount,
                difference=difference,
                explanation=explanation,
            )
        )
    status = (
        "MATCHED"
        if findings
        and all(
            item.disposition is PayrollControlDisposition.MATCHED for item in findings
        )
        else "REVIEW_REQUIRED"
    )
    canonical = request.model_dump(mode="json")
    return PayrollAccountingControlProjection(
        cutoff_at=request.cutoff_at,
        currency=request.currency,
        status=status,
        findings=tuple(findings),
        evidence_digest=_digest(canonical),
    )


async def project_payroll_run_accounting_control(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    payroll_run_id: UUID,
    cutoff_at: datetime,
) -> PayrollAccountingControlProjection:
    """Join an approved Payroll run to its posted, mapped GL evidence."""
    if not context.has_permission(PayrollPermission.ACCOUNTING_READ):
        raise PayrollAuthorizationError("Payroll Accounting permission denied")
    run = await session.scalar(
        select(PayrollRunRecord).where(
            PayrollRunRecord.company_id == context.company.id,
            PayrollRunRecord.id == payroll_run_id,
            PayrollRunRecord.lifecycle == "approved",
        )
    )
    if run is None:
        raise PayrollConflictError("Approved Payroll run was not found")
    consumptions = tuple(
        (
            await session.scalars(
                select(PayrollAccountingConsumptionRecord).where(
                    PayrollAccountingConsumptionRecord.company_id == context.company.id,
                    PayrollAccountingConsumptionRecord.source_id == run.id,
                    PayrollAccountingConsumptionRecord.lifecycle == "posted",
                )
            )
        ).all()
    )
    journal_ids = tuple(row.journal_id for row in consumptions if row.journal_id)
    mappings = tuple(
        (
            await session.scalars(
                select(PayrollAccountingMappingVersion).where(
                    PayrollAccountingMappingVersion.company_id == context.company.id,
                    PayrollAccountingMappingVersion.lifecycle == "approved",
                )
            )
        ).all()
    )
    lines = tuple(
        (
            await session.scalars(
                select(JournalLine)
                .join(Journal, Journal.id == JournalLine.journal_id)
                .where(
                    JournalLine.company_id == context.company.id,
                    JournalLine.journal_id.in_(journal_ids or (None,)),
                    Journal.status == "posted",
                    Journal.effective_date <= cutoff_at.date(),
                )
            )
        ).all()
    )
    by_account: dict[object, Decimal] = {}
    for line in lines:
        by_account[line.account_id] = (
            by_account.get(line.account_id, Decimal(0)) + line.credit - line.debit
        )
    expected = {
        "gross_wages": ("gross_wages", run.aggregate_gross),
        "employee_tax_withholding": (
            "employee_tax_withholding",
            run.aggregate_employee_taxes,
        ),
        "employee_deduction_payable": (
            "employee_deduction_payable",
            run.aggregate_employee_deductions,
        ),
        "employer_payroll_tax_liability": (
            "employer_contribution_liability",
            run.aggregate_employer_contributions,
        ),
        "net_pay_payable": ("net_pay_payable", run.aggregate_net_pay),
    }
    amounts: list[PayrollControlAmount] = []
    for category, (mapping_component, payroll_amount) in expected.items():
        candidates = [
            item for item in mappings if item.component == mapping_component
        ]
        ledger_amount = None
        ledger_digest = None
        if candidates:
            account_ids = {item.account_id for item in candidates}
            ledger_amount = sum(
                (abs(by_account.get(account_id, Decimal(0))) for account_id in account_ids),
                Decimal(0),
            )
            ledger_digest = _digest(sorted(item.mapping_digest for item in candidates))
        amounts.append(
            PayrollControlAmount(
                category=category,
                payroll_amount=payroll_amount,
                general_ledger_amount=ledger_amount,
                payroll_source_digest=run.run_digest,
                ledger_source_digest=ledger_digest,
                payroll_cutoff=cutoff_at,
                ledger_cutoff=cutoff_at if candidates else None,
                source_linked=bool(candidates and journal_ids),
            )
        )
    return reconcile_payroll_accounting(
        PayrollAccountingControlRequest(
            cutoff_at=cutoff_at, currency=run.currency, amounts=tuple(amounts)
        )
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
