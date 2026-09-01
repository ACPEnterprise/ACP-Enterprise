"""Cash, operational obligation, and earned-economics composition.

This module deliberately does not query Migration evidence or calculate an
Accounting balance.  It composes already-admitted, provider-neutral evidence
while preserving the meaning and period of each source fact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

CONTRACT_VERSION: Final = "economics.cash-operational-composition.v1"


class TruthPlane(StrEnum):
    BUSINESS_ECONOMICS = "business_economics"
    OPERATIONAL_AR_AP = "operational_ar_ap"
    ACCOUNTING_CASH = "accounting_cash"


class RecognitionKind(StrEnum):
    WORK_PERFORMED = "work_performed"
    COMMERCIAL_INVOICE = "commercial_invoice"
    OPEN_RECEIVABLE = "open_receivable"
    PAYMENT_ASSERTION = "payment_assertion"
    SETTLEMENT = "settlement"
    CASH_RECEIPT = "cash_receipt"
    DEPOSIT = "deposit"
    EARNED_ECONOMIC_EVIDENCE = "earned_economic_evidence"
    ACCOUNTING_RECOGNITION = "accounting_recognition"
    MATERIAL_PURCHASE = "material_purchase"
    MATERIAL_CONSUMPTION = "material_consumption"
    OPEN_VENDOR_OBLIGATION = "open_vendor_obligation"
    OPEN_CARD_LIABILITY = "open_card_liability"
    VENDOR_SETTLEMENT = "vendor_settlement"
    CARD_SETTLEMENT = "card_settlement"
    BANK_OUTFLOW = "bank_outflow"


_PLANES: Final = {
    RecognitionKind.WORK_PERFORMED: TruthPlane.BUSINESS_ECONOMICS,
    RecognitionKind.EARNED_ECONOMIC_EVIDENCE: TruthPlane.BUSINESS_ECONOMICS,
    RecognitionKind.MATERIAL_CONSUMPTION: TruthPlane.BUSINESS_ECONOMICS,
    RecognitionKind.COMMERCIAL_INVOICE: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.OPEN_RECEIVABLE: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.PAYMENT_ASSERTION: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.SETTLEMENT: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.CASH_RECEIPT: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.DEPOSIT: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.MATERIAL_PURCHASE: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.OPEN_VENDOR_OBLIGATION: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.OPEN_CARD_LIABILITY: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.VENDOR_SETTLEMENT: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.CARD_SETTLEMENT: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.BANK_OUTFLOW: TruthPlane.OPERATIONAL_AR_AP,
    RecognitionKind.ACCOUNTING_RECOGNITION: TruthPlane.ACCOUNTING_CASH,
}


@dataclass(frozen=True, slots=True)
class RecognitionEvidence:
    evidence_id: str
    evidence_digest: str
    source_authority: str
    company_id: UUID
    branch_id: UUID | None
    kind: RecognitionKind
    amount: Decimal
    currency: str
    effective_date: date
    work_period: str | None = None
    cash_period: str | None = None
    accounting_period: str | None = None
    accepted: bool = True
    complete: bool = True

    def validate(self) -> None:
        if not self.accepted:
            raise ValueError("unaccepted evidence cannot enter Economics composition")
        if not self.evidence_id.strip() or not self.source_authority.strip():
            raise ValueError("source authority identity is required")
        if len(self.evidence_digest) != 64:
            raise ValueError("source evidence digest is invalid")
        if self.amount < 0:
            raise ValueError("evidence amount cannot be negative")
        if len(self.currency) != 3 or self.currency != self.currency.upper():
            raise ValueError("currency must be an uppercase ISO-style code")


@dataclass(frozen=True, slots=True)
class CashOperationalComposition:
    company_id: UUID
    branch_id: UUID | None
    currency: str
    totals: dict[str, Decimal]
    evidence_count: int
    incomplete_evidence_ids: tuple[str, ...]
    composition_digest: str


def compose_cash_operational_economics(
    evidence: tuple[RecognitionEvidence, ...],
) -> CashOperationalComposition:
    """Compose distinct totals without allowing one state to imply another."""
    if not evidence:
        raise ValueError("authoritative evidence is required")
    for item in evidence:
        item.validate()
    company_id = evidence[0].company_id
    branch_id = evidence[0].branch_id
    currency = evidence[0].currency
    if any(item.company_id != company_id for item in evidence):
        raise ValueError("cross-Company evidence is prohibited")
    if any(item.branch_id != branch_id for item in evidence):
        raise ValueError("cross-Branch evidence is prohibited")
    if any(item.currency != currency for item in evidence):
        raise ValueError("cross-currency composition is prohibited")

    identities: dict[str, str] = {}
    for item in evidence:
        existing = identities.setdefault(item.evidence_id, item.evidence_digest)
        if existing != item.evidence_digest:
            raise ValueError("contradictory evidence identity fails closed")
    if len(identities) != len(evidence):
        raise ValueError("duplicate source evidence must be admitted exactly once")

    totals = {kind.value: Decimal(0) for kind in RecognitionKind}
    for item in evidence:
        totals[item.kind.value] += item.amount

    canonical = {
        "version": CONTRACT_VERSION,
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "currency": currency,
        "evidence": [
            {
                "id": item.evidence_id,
                "digest": item.evidence_digest,
                "authority": item.source_authority,
                "kind": item.kind.value,
                "plane": _PLANES[item.kind].value,
                "amount": str(item.amount),
                "effective_date": item.effective_date.isoformat(),
                "work_period": item.work_period,
                "cash_period": item.cash_period,
                "accounting_period": item.accounting_period,
                "complete": item.complete,
            }
            for item in sorted(evidence, key=lambda value: value.evidence_id)
        ],
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CashOperationalComposition(
        company_id,
        branch_id,
        currency,
        totals,
        len(evidence),
        tuple(sorted(item.evidence_id for item in evidence if not item.complete)),
        digest,
    )


def recognition_contract() -> dict[str, object]:
    """Machine-readable separation used by APIs, Luminary, and LIA."""
    stages = [
        {
            "kind": kind.value,
            "truth_plane": _PLANES[kind].value,
            "does_not_imply": [
                other.value for other in RecognitionKind if other is not kind
            ],
        }
        for kind in RecognitionKind
    ]
    canonical = {"version": CONTRACT_VERSION, "stages": stages}
    return {
        **canonical,
        "contract_digest": hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "accounting_policy": "cash_basis_authoritative_when_admitted_by_accounting",
        "migration_boundary": "readiness_metadata_only_no_protected_rows",
        "mutation_authority": "none",
    }
