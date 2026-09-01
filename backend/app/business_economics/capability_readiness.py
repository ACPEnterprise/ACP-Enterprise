"""Machine-readable audit of the Business Economics owner-intelligence program."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Final

CAPABILITY_MATRIX_VERSION: Final = "economics.capability-readiness.v2"

_CAPABILITIES: Final = (
    ("source_readiness", "AUTHORITATIVE", "business_economics", ()),
    ("overhead_allocation_authority", "AUTHORITATIVE", "business_economics", ()),
    ("policy_administration_read", "AUTHORITATIVE", "business_economics", ()),
    (
        "policy_draft_activation",
        "POLICY_REQUIRED",
        "business_economics",
        ("owner_finance_policy",),
    ),
    ("job_contribution", "AUTHORITATIVE", "business_economics", ()),
    (
        "allocated_job_profitability",
        "POLICY_REQUIRED",
        "business_economics",
        ("approved_allocation_policy", "complete_allocation_sources"),
    ),
    ("service_category_rollup", "AUTHORITATIVE", "jobs", ()),
    ("customer_rollup", "AUTHORITATIVE", "customers", ()),
    ("branch_rollup", "AUTHORITATIVE", "platform_branch", ()),
    (
        "workforce_cost_composition",
        "PARTIAL",
        "payroll",
        ("explicit_employee_job_attribution",),
    ),
    (
        "material_cost_composition",
        "PARTIAL",
        "inventory_purchasing",
        ("accepted_job_material_cost",),
    ),
    (
        "callback_warranty_economics",
        "SOURCE_REQUIRED",
        "jobs_assets",
        ("authoritative_callback_warranty_relationship",),
    ),
    (
        "service_agreement_economics",
        "SOURCE_REQUIRED",
        "service_agreements",
        ("recognized_financial_and_consumption_evidence",),
    ),
    (
        "revenue_leakage_readiness",
        "PARTIAL",
        "commercial_domains",
        ("accepted_commercial_handoff_dispositions",),
    ),
    ("margin_movement", "AUTHORITATIVE", "business_economics", ()),
    ("bounded_period_comparison", "AUTHORITATIVE", "business_economics", ()),
    (
        "trend_evidence",
        "PARTIAL",
        "business_economics",
        ("three_or_more_comparable_periods",),
    ),
    (
        "capacity_utilization_economics",
        "SOURCE_REQUIRED",
        "scheduling_workforce",
        ("accepted_capacity_measurement_contract",),
    ),
    (
        "cash_working_capital",
        "PARTIAL",
        "accounting_ar_ap_business_economics",
        ("admitted_native_accounting_cash_totals",),
    ),
    (
        "cash_operational_truth_separation",
        "COMPLETED_IN_THIS_PROGRAM",
        "business_economics",
        (),
    ),
    ("operational_ar_readiness", "AUTHORITATIVE", "invoicing", ()),
    ("operational_ap_readiness", "AUTHORITATIVE", "accounts_payable", ()),
    (
        "cash_basis_accounting_totals",
        "EXTERNAL_GATE",
        "accounting_migration",
        ("admitted_native_accounting_report",),
    ),
    ("exception_center", "COMPLETED_IN_THIS_PROGRAM", "business_economics", ()),
    ("owner_dashboard", "AUTHORITATIVE", "business_economics", ()),
    ("luminary_findings", "AUTHORITATIVE", "luminary", ()),
    ("luminary_briefing", "AUTHORITATIVE", "luminary", ()),
    ("beacon_composition", "AUTHORITATIVE", "beacon", ()),
    ("lia_economics_context", "AUTHORITATIVE", "lia", ()),
    ("immutable_result_history", "AUTHORITATIVE", "business_economics", ()),
    (
        "accounting_net_income",
        "DEPENDENCY_BLOCKED",
        "accounting",
        ("native_accounting_reporting_authority",),
    ),
    (
        "real_qbo_evidence",
        "ACTIVE_OWNER_COLLISION",
        "migration",
        ("migration_owned_acquisition",),
    ),
)


def capability_readiness_matrix() -> dict[str, object]:
    capabilities = [
        {
            "capability": capability,
            "state": state,
            "authority_owner": owner,
            "blockers": list(blockers),
        }
        for capability, state, owner, blockers in _CAPABILITIES
    ]
    canonical = {"version": CAPABILITY_MATRIX_VERSION, "capabilities": capabilities}
    return {
        **canonical,
        "matrix_digest": sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "mutation_authority": "none",
        "real_qbo_boundary": "migration_owned",
    }
