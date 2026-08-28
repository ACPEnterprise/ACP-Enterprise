"""All County v1 evidence contracts and current gap assessment."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from ..evidence_acceptance import (
    ACCEPTANCE_DEFINITION_VERSION,
    EvidenceAcceptanceContract,
    GapAssessmentClass,
)


def _contract(
    family: str,
    gap: str,
    facts: tuple[str, ...],
    authorities: tuple[str, ...],
    prohibited: tuple[str, ...] = (),
    *,
    provisional: bool = False,
) -> EvidenceAcceptanceContract:
    return EvidenceAcceptanceContract(
        contract_id=f"all-county.evidence-acceptance.{gap}.v1",
        version=ACCEPTANCE_DEFINITION_VERSION,
        gap_key=gap,
        family_key=family,
        required_facts=facts,
        permitted_authorities=authorities,
        prohibited_evidence_roles=prohibited,
        provisional_allowed=provisional,
    )


_SPECS = (
    (
        "job_lifecycle_cutoff",
        "authoritative_completed_status",
        ("job_id", "status", "completed_at", "completion_event_id"),
        ("acp_jobs_authoritative",),
        ("hcp_source_reported", "qbo_source_reported"),
        False,
    ),
    (
        "job_lifecycle_cutoff",
        "reopen_recompletion_treatment",
        (
            "job_id",
            "lifecycle_event_ids",
            "current_event_id",
            "superseded_event_ids",
            "cancellation_state",
        ),
        ("acp_jobs_authoritative",),
        (),
        False,
    ),
    (
        "revenue_recognition",
        "accepted_earned_job_value",
        (
            "job_id",
            "accepted_earned_value",
            "currency",
            "completion_event_id",
            "acceptance_id",
        ),
        ("acp_finance_accepted_earned_value",),
        (
            "invoice_issued",
            "estimate_value",
            "payment",
            "hcp_source_reported",
            "qbo_source_reported",
        ),
        False,
    ),
    (
        "revenue_recognition",
        "revenue_corrections",
        (
            "job_id",
            "value_revision_id",
            "credit_adjustment_ids",
            "cancellation_treatment",
            "supersedes_revision_id",
        ),
        ("acp_finance_accepted_earned_value",),
        ("invoice_issued",),
        False,
    ),
    (
        "direct_labor_measurement",
        "approved_actual_job_time",
        (
            "job_id",
            "employee_id",
            "actual_duration",
            "time_unit",
            "approval_id",
            "effective_period",
        ),
        ("acp_approved_actual_job_time",),
        (
            "appointment_scheduled_duration",
            "appointment_elapsed_duration",
            "estimated_labor",
        ),
        False,
    ),
    (
        "direct_labor_measurement",
        "technician_participation_identity",
        ("job_id", "employee_id", "participation_id", "role", "effective_period"),
        ("acp_approved_actual_job_time",),
        ("dispatch_assignment_only",),
        False,
    ),
    (
        "direct_labor_measurement",
        "labor_approval_correction",
        ("time_revision_id", "approval_id", "approved_by", "supersedes_revision_id"),
        ("acp_approved_actual_job_time",),
        (),
        False,
    ),
    (
        "direct_labor_measurement",
        "multi_technician_participation",
        ("job_id", "participation_ids", "employee_ids", "nonduplicative_time_identity"),
        ("acp_approved_actual_job_time",),
        ("appointment_assignment_only",),
        False,
    ),
    (
        "labor_burden",
        "worker_class_definitions",
        (
            "worker_class_id",
            "definition_version",
            "effective_period",
            "finance_approval_id",
        ),
        ("company_finance_policy_parameter",),
        (),
        False,
    ),
    (
        "labor_burden",
        "worker_class_assignments",
        ("employee_id", "worker_class_id", "effective_period", "approval_id"),
        ("company_finance_policy_parameter",),
        (),
        False,
    ),
    (
        "labor_burden",
        "standard_burden_rates",
        (
            "worker_class_id",
            "rate",
            "rate_unit",
            "currency",
            "effective_period",
            "finance_approval_id",
        ),
        ("company_finance_policy_parameter",),
        (),
        False,
    ),
    (
        "labor_burden",
        "burden_true_up",
        ("true_up_policy_id", "version", "effective_period", "finance_approval_id"),
        ("company_finance_policy_parameter",),
        (),
        False,
    ),
    (
        "direct_material_costing",
        "job_linked_inventory_issues",
        (
            "job_id",
            "reservation_id",
            "material_issue_id",
            "item_id",
            "quantity",
            "unit",
            "occurred_at",
        ),
        ("acp_inventory_material_issue",),
        ("purchase", "accounts_payable", "qbo_source_reported"),
        False,
    ),
    (
        "direct_material_costing",
        "inventory_cost_layers",
        (
            "material_issue_id",
            "cost_layer_id",
            "unit_cost",
            "currency",
            "valuation_method",
            "cost_acceptance_id",
        ),
        ("acp_inventory_accepted_cost_layer",),
        ("purchase", "accounts_payable"),
        False,
    ),
    (
        "direct_material_costing",
        "material_corrections",
        ("material_issue_id", "reversal_issue_ids", "correction_identity"),
        ("acp_inventory_material_issue",),
        (),
        False,
    ),
    (
        "other_attributable_direct_costs",
        "direct_cost_categories",
        ("category_id", "category_version", "inclusion_state", "finance_approval_id"),
        ("company_finance_policy_parameter",),
        (),
        False,
    ),
    (
        "other_attributable_direct_costs",
        "direct_cost_job_linkage",
        ("job_id", "direct_cost_id", "category_id", "linkage_evidence_id"),
        ("acp_accepted_job_direct_cost",),
        ("purchase_proximity", "accounts_payable_proximity"),
        False,
    ),
    (
        "other_attributable_direct_costs",
        "direct_cost_value_authority",
        (
            "direct_cost_id",
            "accepted_amount",
            "currency",
            "effective_date",
            "correction_ids",
        ),
        ("acp_accepted_job_direct_cost",),
        ("qbo_source_reported", "hcp_source_reported"),
        False,
    ),
    (
        "reconciliation_source_precedence",
        "conflict_identity",
        ("component", "assertion_ids", "reconciliation_key", "value_digests"),
        ("business_economics_reconciliation",),
        (),
        False,
    ),
    (
        "reconciliation_source_precedence",
        "conflict_exclusion",
        ("component", "conflict_id", "exclusion_state", "admission_blocked"),
        ("business_economics_reconciliation",),
        (),
        False,
    ),
    (
        "accounting_reconciliation_admission",
        "accounting_completeness",
        ("evidence_set_id", "expected_count", "observed_count", "complete"),
        ("acp_accounting_quality_attestation",),
        (),
        True,
    ),
    (
        "accounting_reconciliation_admission",
        "accounting_freshness",
        ("evidence_set_id", "as_of", "freshness_rule_id", "current"),
        ("acp_accounting_quality_attestation",),
        (),
        True,
    ),
    (
        "accounting_reconciliation_admission",
        "accounting_reconciliation",
        ("evidence_set_id", "reconciliation_id", "status", "exceptions"),
        ("acp_accounting_quality_attestation",),
        ("qbo_source_reported",),
        True,
    ),
    (
        "accounting_reconciliation_admission",
        "accounting_integrity",
        ("evidence_set_id", "integrity_digest", "integrity_passed"),
        ("acp_accounting_quality_attestation",),
        (),
        True,
    ),
    (
        "accounting_reconciliation_admission",
        "provisional_review_label",
        ("evidence_set_id", "review_status", "result_label"),
        ("acp_accounting_quality_attestation",),
        (),
        True,
    ),
)

ALL_COUNTY_EVIDENCE_CONTRACTS = MappingProxyType(
    {
        gap: _contract(
            family, gap, facts, authorities, prohibited, provisional=provisional
        )
        for family, gap, facts, authorities, prohibited, provisional in _SPECS
    }
)

_SATISFIABLE_NOW = {
    "authoritative_completed_status",
    "reopen_recompletion_treatment",
    "material_corrections",
    "conflict_identity",
    "conflict_exclusion",
}
_FINANCE_PARAMETER = {
    "worker_class_definitions",
    "worker_class_assignments",
    "standard_burden_rates",
    "burden_true_up",
    "direct_cost_categories",
}
_EXTERNAL_RECONCILIATION = {"accounting_reconciliation"}

ALL_COUNTY_GAP_ASSESSMENT = MappingProxyType(
    {
        gap: (
            GapAssessmentClass.SATISFIABLE_NOW
            if gap in _SATISFIABLE_NOW
            else GapAssessmentClass.FINANCE_PARAMETER_REQUIRED
            if gap in _FINANCE_PARAMETER
            else GapAssessmentClass.EXTERNAL_RECONCILIATION_REQUIRED
            if gap in _EXTERNAL_RECONCILIATION
            else GapAssessmentClass.UPSTREAM_CONTRACT_REQUIRED
        )
        for gap in ALL_COUNTY_EVIDENCE_CONTRACTS
    }
)


@dataclass(frozen=True)
class SourceAuthorityMatrixEntry:
    evidence_type: str
    acp_authority: str | None
    accounting_role: str
    hcp_role: str
    qbo_role: str
    current_state: str
    reconciliation_requirement: str


SOURCE_AUTHORITY_MATRIX: Final = (
    SourceAuthorityMatrixEntry(
        "job_lifecycle",
        "acp_jobs_authoritative",
        "not_required",
        "migration_provenance_only",
        "not_authoritative",
        "available",
        "accepted cutover identity required for migrated Jobs",
    ),
    SourceAuthorityMatrixEntry(
        "earned_job_value",
        None,
        "posting facts insufficient for Job earned meaning",
        "source-reported only",
        "quickbooks_online_source_reported",
        "missing_contract",
        "Finance acceptance and correction contract required",
    ),
    SourceAuthorityMatrixEntry(
        "actual_job_time",
        None,
        "not_applicable",
        "source-reported operational evidence only",
        "not_authoritative",
        "missing_contract",
        "approved actual-time and participation contract required",
    ),
    SourceAuthorityMatrixEntry(
        "worker_class_burden",
        None,
        "not_applicable",
        "not_authoritative",
        "not_authoritative",
        "missing_finance_parameters",
        "Finance-approved effective-dated parameters required",
    ),
    SourceAuthorityMatrixEntry(
        "job_material_issue",
        "acp_inventory_material_issue",
        "cost posting alone insufficient",
        "source-reported only",
        "quickbooks_online_source_reported",
        "partial",
        "Job reservation linkage plus accepted cost layer required",
    ),
    SourceAuthorityMatrixEntry(
        "other_direct_cost",
        None,
        "posting facts insufficient for Job/category meaning",
        "source-reported only",
        "quickbooks_online_source_reported",
        "missing_contract",
        "approved category, Job linkage, and accepted value required",
    ),
    SourceAuthorityMatrixEntry(
        "accounting_quality",
        None,
        "quality attestation required",
        "control evidence only",
        "quickbooks_online_source_reported",
        "missing_contract",
        "complete/current/reconciled/integrity attestation required",
    ),
)
