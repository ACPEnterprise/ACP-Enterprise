"""Deterministic Job-level Economics coverage and evidence acquisition queue."""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Any, Final

CONTRACT_VERSION: Final = "economics.job-cost-coverage.v1"


class CoverageState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    SOURCE_REQUIRED = "SOURCE_REQUIRED"
    POLICY_REQUIRED = "POLICY_REQUIRED"
    CONFLICTING = "CONFLICTING"


class ContributionReadiness(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"


def project_job_cost_coverage(
    jobs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    """Attach truthful coverage without treating missing cost as zero."""
    queue: Counter[tuple[str, str, str]] = Counter()
    distribution: Counter[str] = Counter()
    for job in jobs:
        revenue = job.get("invoiced_revenue_minor")
        currency = job.get("currency")
        worked = job.get("accepted_worked_seconds")
        usage_count = int(job.get("material_quantity_evidence_count") or 0)
        material_cost = job.get("material_cost_minor")
        settlement = job.get("settlement_applied_minor")
        category = job.get("service_category")
        coverage: dict[str, dict[str, str]] = {
            "invoiced_revenue": _state(
                revenue is not None,
                "issued_invoice",
                "issued_invoice_for_job",
            ),
            "settlement": _state(
                settlement is not None,
                "verified_payment_application",
                "verified_payment_application_for_invoice",
            ),
            "accepted_work_hours": _state(
                worked is not None,
                "accepted_job_work_interval",
                "accepted_employee_job_work_interval",
            ),
            "wage_cost": {
                "state": CoverageState.SOURCE_REQUIRED.value,
                "authority": "payroll_compensation_and_accepted_workweek",
                "requirement": (
                    "effective_compensation_plus_regular_overtime_job_allocation"
                    if worked is not None
                    else "accepted_employee_job_work_interval_then_compensation"
                ),
            },
            "material_usage": _state(
                usage_count > 0,
                "inventory_material_issue",
                "job_attributed_inventory_issue_or_authoritative_no_usage",
            ),
            "material_cost": {
                "state": (
                    CoverageState.AVAILABLE.value
                    if material_cost is not None
                    else CoverageState.SOURCE_REQUIRED.value
                ),
                "authority": "inventory_valuation_layer",
                "requirement": (
                    "satisfied"
                    if material_cost is not None
                    else "valued_job_material_issue_or_authoritative_no_usage"
                ),
            },
            "other_direct_cost": {
                "state": CoverageState.SOURCE_REQUIRED.value,
                "authority": "job_attributed_direct_expense",
                "requirement": "attributable_cost_or_authoritative_not_applicable",
            },
            "service_category": _state(
                category is not None,
                "canonical_job_type_code",
                "canonical_service_category_mapping",
            ),
            "customer": _state(
                bool(job.get("customer_id")),
                "job_customer_foreign_key",
                "authoritative_customer_binding",
            ),
            "branch": _state(
                bool(job.get("branch_id")),
                "job_branch_foreign_key",
                "authoritative_branch_binding",
            ),
        }
        if revenue is not None and currency is None:
            coverage["invoiced_revenue"] = {
                "state": CoverageState.CONFLICTING.value,
                "authority": "issued_invoice",
                "requirement": "resolve_multiple_invoice_currencies",
            }
        states = {item["state"] for item in coverage.values()}
        if CoverageState.CONFLICTING.value in states:
            readiness = ContributionReadiness.CONFLICTING
        elif revenue is None:
            readiness = ContributionReadiness.INSUFFICIENT
        elif all(
            coverage[key]["state"] == CoverageState.AVAILABLE.value
            for key in (
                "wage_cost",
                "material_cost",
                "other_direct_cost",
            )
        ):
            readiness = ContributionReadiness.READY
        else:
            readiness = ContributionReadiness.PARTIAL
        job["cost_coverage"] = coverage
        job["contribution_readiness"] = readiness.value
        job["direct_contribution_minor"] = None
        distribution[readiness.value] += 1
        for family, item in coverage.items():
            if item["state"] != CoverageState.AVAILABLE.value:
                owner = (
                    "OWNER"
                    if item["state"] == CoverageState.POLICY_REQUIRED.value
                    else "MACHINE_ACQUISITION"
                )
                queue[(family, item["requirement"], owner)] += 1

    ordered_queue = [
        {
            "family": family,
            "exact_requirement": requirement,
            "responsible_party": responsible_party,
            "affected_job_count": count,
        }
        for (family, requirement, responsible_party), count in sorted(
            queue.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    summary: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "contribution_readiness": {
            state.value: distribution[state.value] for state in ContributionReadiness
        },
        "data_completeness_queue": ordered_queue,
        "missing_cost_is_zero": False,
    }
    return jobs, summary


def _state(
    available: bool, authority: str, missing_requirement: str
) -> dict[str, str]:
    return {
        "state": (
            CoverageState.AVAILABLE.value
            if available
            else CoverageState.SOURCE_REQUIRED.value
        ),
        "authority": authority,
        "requirement": "satisfied" if available else missing_requirement,
    }
