from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Union

from .reconciliation import ReconciliationState

EvidenceValue = Union[str, Decimal, bool, date]  # noqa: UP007 - Python 3.9 test host


class AssertionSource(str, Enum):
    QBO = "qbo"
    CONTROL_REPORT = "control_report"
    HCP = "hcp"
    AMEX_ISSUER = "amex_issuer"


@dataclass(frozen=True)
class EvidenceAssertion:
    source: AssertionSource
    evidence_id: str
    subject_key: str
    fact_name: str
    value: EvidenceValue

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.subject_key or not self.fact_name:
            raise ValueError("evidence identity, subject, and fact are required")


@dataclass(frozen=True)
class ReconciliationFinding:
    finding_id: str
    subject_key: str
    fact_name: str
    source_assertion: EvidenceAssertion | None
    control_assertion: EvidenceAssertion | None
    state: ReconciliationState
    winner: None = None

    def __post_init__(self) -> None:
        if self.winner is not None:
            raise ValueError("acquisition reconciliation cannot choose a winner")


class ReconciliationWorkbench:
    """Compare assertions without changing either evidence source."""

    @staticmethod
    def compare(
        *,
        finding_id: str,
        source: EvidenceAssertion | None,
        control: EvidenceAssertion | None,
    ) -> ReconciliationFinding:
        assertion = source or control
        if assertion is None:
            raise ValueError("at least one evidence assertion is required")
        if source is None:
            state = ReconciliationState.MISSING_SOURCE_EVIDENCE
        elif control is None:
            state = ReconciliationState.MISSING_CONTROL_EVIDENCE
        else:
            if (source.subject_key, source.fact_name) != (
                control.subject_key,
                control.fact_name,
            ):
                raise ValueError("assertions must address the same fact")
            state = (
                ReconciliationState.MATCHED
                if source.value == control.value
                else ReconciliationState.EXCEPTION
            )
        return ReconciliationFinding(
            finding_id=finding_id,
            subject_key=assertion.subject_key,
            fact_name=assertion.fact_name,
            source_assertion=source,
            control_assertion=control,
            state=state,
        )


class AmexActivityKind(str, Enum):
    CHARGE = "charge"
    CREDIT = "credit"
    PAYMENT = "payment"
    FEE = "fee"
    INTEREST = "interest"


@dataclass(frozen=True)
class AmexAccountEvidence:
    qbo_account_id: str
    envelope_sha256: str
    name_as_reported: str
    account_type_as_reported: str
    account_subtype_as_reported: str | None
    currency: str | None


@dataclass(frozen=True)
class AmexActivityEvidence:
    qbo_native_type: str
    qbo_native_id: str
    envelope_sha256: str
    account_id: str
    activity_kind: AmexActivityKind
    amount_as_reported: Decimal
    transaction_date: date | None
    posting_or_source_date_as_reported: date | None
    payee_or_vendor_id: str | None
    qbo_classification_id: str | None
    memo_or_reference: str | None
    native_link_ids: tuple[str, ...]
    qbo_job_or_customer_id: str | None
    material_attribution_id: str | None
    reconciliation_state: ReconciliationState

    @property
    def missing_job_attribution(self) -> bool:
        return self.qbo_job_or_customer_id is None

    @property
    def missing_material_attribution(self) -> bool:
        return self.material_attribution_id is None


@dataclass(frozen=True)
class AmexReconciliationItem:
    qbo_activity: AmexActivityEvidence | None
    issuer_assertion: EvidenceAssertion | None
    finding: ReconciliationFinding

    def __post_init__(self) -> None:
        if self.finding.winner is not None:
            raise ValueError("AMEX reconciliation cannot choose a winner")
