from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from .contracts import QboSourceEnvelope

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class EconomicsEvidenceCategory(str, Enum):
    REVENUE_ASSERTION = "revenue_assertion"
    SETTLEMENT_ASSERTION = "settlement_assertion"
    PROCUREMENT_ASSERTION = "procurement_assertion"
    AP_ASSERTION = "ap_assertion"
    GL_RECONCILIATION_ASSERTION = "gl_reconciliation_assertion"
    OPERATIONAL_CONTEXT = "operational_context"


class EconomicsEvidenceState(str, Enum):
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class ProfitabilityComponent(str, Enum):
    REVENUE = "revenue"
    DIRECT_LABOR = "direct_labor"
    DIRECT_MATERIAL = "direct_material"
    EQUIPMENT = "equipment"
    TRUCK = "truck"
    OVERHEAD = "overhead"


@dataclass(frozen=True)
class QboEconomicsAssertion:
    assertion_id: str
    category: EconomicsEvidenceCategory
    state: EconomicsEvidenceState
    source_authority: str
    acceptance_status: str
    source_manifest_sha256: str
    source_envelope_sha256: str
    native_entity_type: str
    native_id: str
    raw_sha256: str
    relationship_ids: tuple[str, ...]
    reported_fields: Mapping[str, object]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for digest in (
            self.source_manifest_sha256,
            self.source_envelope_sha256,
            self.raw_sha256,
        ):
            if not _SHA256.fullmatch(digest):
                raise ValueError("immutable source digest is required")
        if self.source_authority != "quickbooks_online_source_reported":
            raise ValueError("QBO source-reported authority is required")
        if self.acceptance_status != "unreconciled_not_enterprise_accepted":
            raise ValueError("unreconciled evidence cannot become accepted truth")
        object.__setattr__(
            self, "reported_fields", MappingProxyType(dict(self.reported_fields))
        )


@dataclass(frozen=True)
class ProfitabilityReadiness:
    component: ProfitabilityComponent
    state: EconomicsEvidenceState
    evidence_ids: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class QboEconomicsEvidenceAssessment:
    source_manifest_sha256: str
    source_manifest_state: str
    assertions: tuple[QboEconomicsAssertion, ...]
    profitability_readiness: tuple[ProfitabilityReadiness, ...]
    assessment_sha256: str


_CATEGORY_BY_ENTITY: dict[str, EconomicsEvidenceCategory] = {
    "invoice": EconomicsEvidenceCategory.REVENUE_ASSERTION,
    "credit_memo": EconomicsEvidenceCategory.REVENUE_ASSERTION,
    "refund_receipt": EconomicsEvidenceCategory.REVENUE_ASSERTION,
    "payment": EconomicsEvidenceCategory.SETTLEMENT_ASSERTION,
    "sales_receipt": EconomicsEvidenceCategory.SETTLEMENT_ASSERTION,
    "purchase": EconomicsEvidenceCategory.PROCUREMENT_ASSERTION,
    "vendor_credit": EconomicsEvidenceCategory.PROCUREMENT_ASSERTION,
    "credit_card_payment": EconomicsEvidenceCategory.PROCUREMENT_ASSERTION,
    "bill": EconomicsEvidenceCategory.AP_ASSERTION,
    "bill_payment": EconomicsEvidenceCategory.AP_ASSERTION,
    "account": EconomicsEvidenceCategory.GL_RECONCILIATION_ASSERTION,
    "journal_entry": EconomicsEvidenceCategory.GL_RECONCILIATION_ASSERTION,
    "deposit": EconomicsEvidenceCategory.GL_RECONCILIATION_ASSERTION,
    "transfer": EconomicsEvidenceCategory.GL_RECONCILIATION_ASSERTION,
}


def assess_qbo_economics_evidence(
    *,
    source_manifest_sha256: str,
    source_manifest_state: str,
    envelopes: tuple[tuple[str, QboSourceEnvelope], ...],
) -> QboEconomicsEvidenceAssessment:
    if not _SHA256.fullmatch(source_manifest_sha256):
        raise ValueError("source manifest digest is invalid")
    if source_manifest_state not in {"complete", "partial"}:
        raise ValueError("sealed complete or partial source manifest is required")

    assertions = tuple(
        sorted(
            (
                _assertion(source_manifest_sha256, envelope_sha256, envelope)
                for envelope_sha256, envelope in envelopes
            ),
            key=lambda item: (
                item.category.value,
                item.native_entity_type,
                item.native_id,
                item.source_envelope_sha256,
            ),
        )
    )
    readiness = _profitability_readiness(assertions, source_manifest_state)
    canonical = {
        "source_manifest_sha256": source_manifest_sha256,
        "source_manifest_state": source_manifest_state,
        "assertions": [
            {
                "assertion_id": item.assertion_id,
                "category": item.category.value,
                "state": item.state.value,
                "source_envelope_sha256": item.source_envelope_sha256,
                "raw_sha256": item.raw_sha256,
                "limitations": list(item.limitations),
            }
            for item in assertions
        ],
        "profitability_readiness": [
            {
                "component": item.component.value,
                "state": item.state.value,
                "evidence_ids": list(item.evidence_ids),
                "missing_requirements": list(item.missing_requirements),
            }
            for item in readiness
        ],
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return QboEconomicsEvidenceAssessment(
        source_manifest_sha256=source_manifest_sha256,
        source_manifest_state=source_manifest_state,
        assertions=assertions,
        profitability_readiness=readiness,
        assessment_sha256=digest,
    )


def _assertion(
    manifest_sha256: str, envelope_sha256: str, envelope: QboSourceEnvelope
) -> QboEconomicsAssertion:
    if not _SHA256.fullmatch(envelope_sha256):
        raise ValueError("source envelope digest is invalid")
    category = _CATEGORY_BY_ENTITY.get(
        envelope.native_entity_type, EconomicsEvidenceCategory.OPERATIONAL_CONTEXT
    )
    limitations = {
        "source_reported_not_enterprise_accepted",
        "control_reconciliation_required",
    }
    if category == EconomicsEvidenceCategory.PROCUREMENT_ASSERTION:
        limitations.update(
            {"job_attribution_unknown", "material_consumption_not_proven"}
        )
    if category == EconomicsEvidenceCategory.REVENUE_ASSERTION:
        limitations.add("revenue_recognition_not_finance_accepted")
    if category == EconomicsEvidenceCategory.SETTLEMENT_ASSERTION:
        limitations.add("settlement_does_not_duplicate_revenue")
    if category == EconomicsEvidenceCategory.OPERATIONAL_CONTEXT:
        limitations.add("not_a_financial_measurement")
    identity = hashlib.sha256(
        f"{manifest_sha256}:{envelope_sha256}:{envelope.native_entity_type}:{envelope.native_id}".encode()
    ).hexdigest()
    return QboEconomicsAssertion(
        assertion_id=f"qbo-economics:{identity}",
        category=category,
        state=EconomicsEvidenceState.PARTIAL,
        source_authority="quickbooks_online_source_reported",
        acceptance_status="unreconciled_not_enterprise_accepted",
        source_manifest_sha256=manifest_sha256,
        source_envelope_sha256=envelope_sha256,
        native_entity_type=envelope.native_entity_type,
        native_id=envelope.native_id,
        raw_sha256=envelope.raw_sha256,
        relationship_ids=envelope.relationship_ids,
        reported_fields=envelope.source_accounting_meaning,
        limitations=tuple(sorted(limitations)),
    )


def _profitability_readiness(
    assertions: tuple[QboEconomicsAssertion, ...], manifest_state: str
) -> tuple[ProfitabilityReadiness, ...]:
    category_ids: dict[EconomicsEvidenceCategory, tuple[str, ...]] = {}
    for category in EconomicsEvidenceCategory:
        category_ids[category] = tuple(
            item.assertion_id for item in assertions if item.category == category
        )
    revenue_ids = category_ids[EconomicsEvidenceCategory.REVENUE_ASSERTION]
    purchase_ids = category_ids[EconomicsEvidenceCategory.PROCUREMENT_ASSERTION]
    definitions = (
        (
            ProfitabilityComponent.REVENUE,
            revenue_ids,
            ("finance_accepted_revenue_basis", "control_reconciliation"),
            "QBO revenue-shaped records are source assertions, not accepted revenue.",
        ),
        (
            ProfitabilityComponent.DIRECT_MATERIAL,
            purchase_ids,
            ("job_consumption_linkage", "approved_costing_layer", "returns"),
            "Purchases remain unassigned and do not prove Job material consumption.",
        ),
        (
            ProfitabilityComponent.DIRECT_LABOR,
            (),
            ("authoritative_paid_time", "productive_job_time", "approved_burden"),
            "QBO source acquisition does not establish measured direct labor.",
        ),
        (
            ProfitabilityComponent.EQUIPMENT,
            (),
            ("asset_utilization", "approved_equipment_cost"),
            "Equipment utilization and cost require their owning source.",
        ),
        (
            ProfitabilityComponent.TRUCK,
            (),
            ("fleet_activity", "approved_truck_cost_driver"),
            "Truck cost requires fleet evidence and approved policy.",
        ),
        (
            ProfitabilityComponent.OVERHEAD,
            (),
            ("finance_approved_pool", "versioned_allocation_policy"),
            "Overhead requires Finance-approved pools and allocation policy.",
        ),
    )
    return tuple(
        ProfitabilityReadiness(
            component=component,
            state=(
                EconomicsEvidenceState.PARTIAL
                if evidence_ids and manifest_state == "complete"
                else EconomicsEvidenceState.UNKNOWN
            ),
            evidence_ids=evidence_ids,
            missing_requirements=tuple(
                sorted(
                    (*missing,)
                    + (
                        ("complete_source_manifest",)
                        if manifest_state == "partial"
                        else ()
                    )
                )
            ),
            explanation=explanation,
        )
        for component, evidence_ids, missing, explanation in definitions
    )
