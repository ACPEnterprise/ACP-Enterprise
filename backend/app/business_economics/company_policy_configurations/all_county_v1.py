"""Owner-approved All County Finance Policy v1 activation candidate.

The factory requires authoritative tenant and approver identities. Importing this
module never activates or persists policy.
"""

from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Final
from uuid import UUID, uuid5

from ..policy_authority import (
    POLICY_DEFINITION_VERSION,
    CompanyPolicyVersion,
    PolicyDisposition,
    PolicyLifecycle,
    PolicyParameterGap,
    PolicySnapshot,
    build_policy_snapshot,
    canonical_digest,
    seal_policy,
    seal_policy_gap,
)

CONFIGURATION_ID: Final = "all-county.finance-policy.v1"
COMPANY_REFERENCE: Final = "all-county-plumbing-and-leak"
POLICY_VERSION: Final = 1
EFFECTIVE_START: Final = date(2026, 8, 27)
METRIC_ID: Final = "direct_job_contribution_accrual_before_overhead"
METRIC_NAME: Final = "DIRECT JOB CONTRIBUTION — ACCRUAL BASIS — BEFORE OVERHEAD"

SELECTED_STRATEGIES = MappingProxyType(
    {
        "job_lifecycle_cutoff": "completed_only",
        "revenue_recognition": "accepted_earned_value_at_completion",
        "direct_labor_measurement": "approved_actual_job_time",
        "labor_burden": "standard_by_worker_class",
        "direct_material_costing": "accepted_inventory_issue_layers",
        "other_attributable_direct_costs": "category_inclusion_exclusion",
        "reconciliation_source_precedence": "reject_conflicting_component",
        "accounting_reconciliation_admission": "integrity_reconciled_provisional",
    }
)
DEFERRED_FAMILIES: Final = (
    "payment_settlement_acceptance",
    "overhead_pool_definitions",
    "overhead_allocation",
    "monetary_materiality",
)

_GAPS = {
    "job_lifecycle_cutoff": {
        "authoritative_completed_status": "authoritative Job Completed status and lifecycle identity",
        "reopen_recompletion_treatment": "reopen, recompletion, cancellation, and late-evidence treatment",
    },
    "revenue_recognition": {
        "accepted_earned_job_value": "accepted earned Job value source and contract",
        "revenue_corrections": "cancellation, credit, adjustment, partial-work, and later-correction treatment",
    },
    "direct_labor_measurement": {
        "approved_actual_job_time": "approved actual Job-time authority",
        "technician_participation_identity": "authoritative technician participation identity",
        "labor_approval_correction": "labor approval and append-only correction contract",
        "multi_technician_participation": "authoritative multi-technician participation evidence",
    },
    "labor_burden": {
        "worker_class_definitions": "approved worker-class definitions",
        "worker_class_assignments": "effective-dated worker-to-class assignments",
        "standard_burden_rates": "approved effective-dated standard burden rates",
        "burden_true_up": "approved burden true-up and correction rules",
    },
    "direct_material_costing": {
        "job_linked_inventory_issues": "accepted Job-linked inventory issue evidence",
        "inventory_cost_layers": "authoritative accepted cost-layer and value evidence",
        "material_corrections": "material correction and reversal treatment",
    },
    "other_attributable_direct_costs": {
        "direct_cost_categories": "explicit approved direct-cost inclusion and exclusion categories",
        "direct_cost_job_linkage": "accepted Job linkage for each approved category",
        "direct_cost_value_authority": "accepted cost evidence for each linked direct cost",
    },
    "reconciliation_source_precedence": {
        "conflict_identity": "accepted semantic conflict and component identities",
        "conflict_exclusion": "deterministic exclusion and reject-or-limit behavior without source precedence",
    },
    "accounting_reconciliation_admission": {
        "accounting_completeness": "Accounting completeness requirement",
        "accounting_freshness": "effective-dated Accounting freshness/currentness rule",
        "accounting_reconciliation": "Accounting reconciliation requirement",
        "accounting_integrity": "Accounting integrity-passed requirement",
        "provisional_review_label": "reviewed versus UNREVIEWED / PROVISIONAL labeling semantics",
    },
}


@dataclass(frozen=True)
class IntendedMetricDefinition:
    metric_id: str
    display_name: str
    basis: str
    included_components: tuple[str, ...]
    excluded_meanings: tuple[str, ...]


@dataclass(frozen=True)
class AllCountyPolicyV1Bundle:
    configuration_id: str
    company_reference: str
    company_id: UUID
    approver_user_id: UUID
    approved_at: datetime
    effective_start: date
    decision_digest: str
    policies: tuple[CompanyPolicyVersion, ...]
    parameter_gaps: tuple[PolicyParameterGap, ...]
    metric: IntendedMetricDefinition
    snapshot: PolicySnapshot


def build_all_county_policy_v1(
    *, company_id: UUID, approver_user_id: UUID, approved_at: datetime
) -> AllCountyPolicyV1Bundle:
    """Seal the approved configuration for supplied authoritative identities."""
    decision = {
        "configuration_id": CONFIGURATION_ID,
        "company_reference": COMPANY_REFERENCE,
        "effective_start": EFFECTIVE_START.isoformat(),
        "selected": dict(SELECTED_STRATEGIES),
        "deferred": DEFERRED_FAMILIES,
        "metric_id": METRIC_ID,
        "decision_source": "eco-all-county-finance-policy-v1-decisions.md",
    }
    decision_digest = canonical_digest(decision)
    gaps = tuple(
        seal_policy_gap(
            gap_id=uuid5(company_id, f"{CONFIGURATION_ID}:gap:{family}:{gap_key}"),
            company_id=company_id,
            branch_id=None,
            family_key=family,
            gap_key=gap_key,
            requirement=requirement,
            authority_dependency=f"{CONFIGURATION_ID}:authority:{family}:{gap_key}",
            effective_start=EFFECTIVE_START,
            registered_by_user_id=approver_user_id,
            registered_at=approved_at,
            decision_evidence_digest=decision_digest,
        )
        for family, family_gaps in sorted(_GAPS.items())
        for gap_key, requirement in sorted(family_gaps.items())
    )
    gap_refs = {
        family: tuple(str(gap.gap_id) for gap in gaps if gap.family_key == family)
        for family in (*SELECTED_STRATEGIES, *DEFERRED_FAMILIES)
    }
    policies = tuple(
        sorted(
            (
                *(
                    _policy(
                        company_id,
                        approver_user_id,
                        approved_at,
                        decision_digest,
                        family,
                        strategy,
                        gap_refs[family],
                        False,
                    )
                    for family, strategy in SELECTED_STRATEGIES.items()
                ),
                *(
                    _policy(
                        company_id,
                        approver_user_id,
                        approved_at,
                        decision_digest,
                        family,
                        None,
                        (),
                        True,
                    )
                    for family in DEFERRED_FAMILIES
                ),
            ),
            key=lambda policy: policy.family_key,
        )
    )
    metric = IntendedMetricDefinition(
        metric_id=METRIC_ID,
        display_name=METRIC_NAME,
        basis="accrual_before_overhead",
        included_components=(
            "accepted_recognized_job_revenue",
            "approved_actual_direct_labor",
            "approved_standard_worker_class_burden",
            "accepted_job_linked_direct_material",
            "accepted_specifically_attributable_direct_costs",
        ),
        excluded_meanings=(
            "net_profit",
            "fully_loaded_profit",
            "technician_profitability",
            "company_profitability",
            "cash_basis_contribution",
        ),
    )
    snapshot = build_policy_snapshot(
        policies,
        company_id=company_id,
        branch_id=None,
        subject_identity=f"metric:{METRIC_ID}",
        reconciliation_key=f"company-policy:{CONFIGURATION_ID}",
        as_of=EFFECTIVE_START,
        required_families=tuple(policy.family_key for policy in policies),
        parameter_gaps=gaps,
    )
    return AllCountyPolicyV1Bundle(
        CONFIGURATION_ID,
        COMPANY_REFERENCE,
        company_id,
        approver_user_id,
        approved_at,
        EFFECTIVE_START,
        decision_digest,
        policies,
        gaps,
        metric,
        snapshot,
    )


def _policy(
    company_id: UUID,
    approver_user_id: UUID,
    approved_at: datetime,
    decision_digest: str,
    family: str,
    strategy: str | None,
    evidence_refs: tuple[str, ...],
    deferred: bool,
) -> CompanyPolicyVersion:
    return seal_policy(
        policy_id=uuid5(
            company_id, f"{CONFIGURATION_ID}:policy:{family}:v{POLICY_VERSION}"
        ),
        company_id=company_id,
        branch_id=None,
        family_key=family,
        policy_version=POLICY_VERSION,
        disposition=PolicyDisposition.DEFERRED
        if deferred
        else PolicyDisposition.SELECTED,
        strategy_key=None if deferred else strategy,
        parameters={},
        evidence_acceptance_rule_refs=evidence_refs,
        effective_start=EFFECTIVE_START,
        effective_end=None,
        lifecycle=PolicyLifecycle.APPROVED,
        definition_version=POLICY_DEFINITION_VERSION,
        approved_by_user_id=approver_user_id,
        approved_at=approved_at,
        decision_evidence_digest=decision_digest,
        supersedes_policy_id=None,
    )
