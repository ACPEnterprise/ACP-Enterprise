"""Fail-closed source semantics used before Economics measurement admission."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EconomicMeaning(StrEnum):
    REVENUE_EVIDENCE = "revenue_evidence"
    SETTLEMENT_EVIDENCE = "settlement_evidence"
    DIRECT_COST_EVIDENCE = "direct_cost_evidence"
    OPERATIONAL_ONLY = "operational_only"
    POLICY_REQUIRED = "policy_required"
    SOURCE_REQUIRED = "source_required"


@dataclass(frozen=True, slots=True)
class SourceSemantic:
    source_type: str
    meaning: EconomicMeaning
    limitation: str
    accounting_mutation_authority: str = "none"


_SEMANTICS = {
    "accepted_earned_revenue": SourceSemantic(
        "accepted_earned_revenue",
        EconomicMeaning.REVENUE_EVIDENCE,
        "Requires admitted revenue-recognition authority; settlement is separate.",
    ),
    "invoice": SourceSemantic(
        "invoice",
        EconomicMeaning.POLICY_REQUIRED,
        "Invoice issuance is not revenue unless approved recognition policy admits it.",
    ),
    "payment": SourceSemantic(
        "payment",
        EconomicMeaning.SETTLEMENT_EVIDENCE,
        "Payment is settlement evidence and must not duplicate earned revenue.",
    ),
    "estimate": SourceSemantic(
        "estimate",
        EconomicMeaning.OPERATIONAL_ONLY,
        "An Estimate is commercial evidence, not realized revenue.",
    ),
    "inventory_transfer": SourceSemantic(
        "inventory_transfer",
        EconomicMeaning.OPERATIONAL_ONLY,
        "A custody transfer is neither income nor expense.",
    ),
    "purchase_order_or_receipt": SourceSemantic(
        "purchase_order_or_receipt",
        EconomicMeaning.OPERATIONAL_ONLY,
        "Purchasing evidence is not automatically Accounting expense or Job cost.",
    ),
    "accepted_job_material_cost": SourceSemantic(
        "accepted_job_material_cost",
        EconomicMeaning.DIRECT_COST_EVIDENCE,
        "Requires admitted costing and Job attribution authority.",
    ),
    "service_agreement_billing_readiness": SourceSemantic(
        "service_agreement_billing_readiness",
        EconomicMeaning.SOURCE_REQUIRED,
        "Billing readiness and enrollment are not recognized revenue.",
    ),
    "callback_label": SourceSemantic(
        "callback_label",
        EconomicMeaning.SOURCE_REQUIRED,
        "A label cannot establish corrective-work identity, incremental cost, or causality.",
    ),
}


def classify_source_semantics(source_type: str) -> SourceSemantic:
    try:
        return _SEMANTICS[source_type]
    except KeyError as error:
        raise ValueError(
            "source type has no accepted Economics semantic contract"
        ) from error
