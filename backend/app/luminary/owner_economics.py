"""Pure, deterministic owner Economics intelligence over admitted projections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Final, cast
from uuid import UUID, uuid5

from app.business_economics.source_completeness import source_completeness_matrix

CONTRACT_VERSION: Final = "luminary.owner-economics-readonly.v1"
ENGINE_VERSION: Final = "luminary.owner-economics-engine.v1"
_NAMESPACE = UUID("51a21f44-2297-5be1-bfe8-50c57c79813c")


class AnalysisReadiness(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    SOURCE_MISSING = "SOURCE_MISSING"
    PROVIDER_UNSUPPORTED = "PROVIDER_UNSUPPORTED"
    REQUIRES_OWNER_INPUT = "REQUIRES_OWNER_INPUT"
    REQUIRES_ACCOUNTANT_INPUT = "REQUIRES_ACCOUNTANT_INPUT"
    POLICY_REQUIRED = "POLICY_REQUIRED"


class RecommendationFamily(StrEnum):
    PRICING = "PRICING"
    OPERATING_EFFICIENCY = "OPERATING_EFFICIENCY"
    MATERIAL_PROCUREMENT = "MATERIAL_PROCUREMENT"
    SERVICE_MIX = "SERVICE_MIX"
    SALES_CONVERSION = "SALES_CONVERSION"
    COST_STRUCTURE = "COST_STRUCTURE"


class ScenarioKind(StrEnum):
    PRICE_PERCENT = "PRICE_PERCENT"
    LABOR_EFFICIENCY_PERCENT = "LABOR_EFFICIENCY_PERCENT"
    MATERIAL_COST_PERCENT = "MATERIAL_COST_PERCENT"
    AVERAGE_TICKET_PERCENT = "AVERAGE_TICKET_PERCENT"
    CLOSE_RATE_PERCENT = "CLOSE_RATE_PERCENT"
    ADD_TRUCK = "ADD_TRUCK"


@dataclass(frozen=True, slots=True)
class ScenarioAssumption:
    kind: ScenarioKind
    change_basis_points: int | None = None

    def __post_init__(self) -> None:
        if self.kind in {ScenarioKind.CLOSE_RATE_PERCENT, ScenarioKind.ADD_TRUCK}:
            if self.change_basis_points is not None:
                raise ValueError("unsupported scenario cannot imply a numeric result")
        elif (
            self.change_basis_points is None
            or not -10_000 <= self.change_basis_points <= 10_000
        ):
            raise ValueError("scenario change must be between -100% and 100%")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: object) -> list[dict[str, Any]]:
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _readiness(workspace: dict[str, object]) -> AnalysisReadiness:
    quality = str(workspace.get("quality_state", "unavailable"))
    if quality == "conflicting":
        return AnalysisReadiness.CONFLICTING_EVIDENCE
    if quality == "unavailable":
        native = _mapping(workspace.get("native_evidence"))
        if int(native.get("admitted_reference_count") or 0) > 0:
            return AnalysisReadiness.PARTIAL
        return AnalysisReadiness.SOURCE_MISSING
    if quality in {"partial", "stale"}:
        return AnalysisReadiness.PARTIAL
    return AnalysisReadiness.READY


def _confidence(workspace: dict[str, object]) -> dict[str, object]:
    jobs = _rows(workspace.get("jobs"))
    scores = [int(item.get("confidence_percent") or 0) for item in jobs]
    completeness = str(workspace.get("quality_state", "unavailable"))
    native = _mapping(workspace.get("native_evidence"))
    native_families = _mapping(native.get("families"))
    native_states = [
        str(_mapping(item).get("state")) for item in native_families.values()
    ]
    native_count = int(native.get("admitted_reference_count") or 0)
    score = (
        min(scores)
        if scores
        else (
            0
            if "CONFLICTING" in native_states
            else 70
            if native_count and "PARTIAL" in native_states
            else 80
            if native_count
            else 0
        )
    )
    if completeness == "partial":
        score = min(score, 70)
    elif completeness == "stale":
        score = min(score, 50)
    elif completeness == "conflicting":
        score = 0
    return {
        "score_percent": score,
        "method": "minimum_admitted_job_confidence_with_quality_caps",
        "factors": {
            "source_authority": (
                "admitted_business_economics_only"
                if jobs
                else "accepted_acp_native_owning_domain_facts"
                if native_count
                else "unavailable"
            ),
            "completeness": completeness,
            "recency": "current" if completeness == "complete" else completeness,
            "reconciliation": "conflicting"
            if completeness == "conflicting"
            else "preserved",
            "sample_size": len(jobs) or native_count,
            "allocation_dependence": not bool(
                workspace.get("fully_allocated_available")
            ),
            "inference_burden": "bounded_association_only",
        },
    }


def _facts(
    workspace: dict[str, object],
    *,
    company_id: UUID,
    branch_id: UUID | None,
    as_of: datetime,
) -> list[dict[str, object]]:
    totals = _mapping(workspace.get("totals"))
    period = _mapping(workspace.get("period"))
    currency = str(workspace.get("currency") or "USD")
    jobs = _rows(workspace.get("jobs"))
    native = _mapping(workspace.get("native_evidence"))
    native_summary = _mapping(native.get("summary"))
    native_jobs = _rows(native.get("jobs"))
    references = [
        {
            "record_type": "profitability_result",
            "record_id": str(item.get("result_id")),
            "digest": str(item.get("result_digest")),
        }
        for item in jobs
        if item.get("result_id") and item.get("result_digest")
    ]
    native_references = [
        reference for job in native_jobs for reference in _rows(job.get("references"))
    ]
    fact_specs = (
        ("REVENUE", "revenue", "minor_currency"),
        ("DIRECT_LABOR", "labor", "minor_currency"),
        ("DIRECT_MATERIAL", "materials", "minor_currency"),
        ("OTHER_DIRECT_COST", "equipment", "minor_currency"),
        ("MARGIN", "gross_profit", "minor_currency"),
        ("OVERHEAD", "overhead", "minor_currency"),
    )
    facts = []
    for family, key, unit in fact_specs:
        value = (
            sum(
                item
                for item in (totals.get("equipment"), totals.get("truck"))
                if isinstance(item, int)
            )
            if key == "equipment"
            and all(
                isinstance(totals.get(item), int) for item in ("equipment", "truck")
            )
            else totals.get(key)
        )
        native_key = {
            "revenue": "invoiced_revenue_minor",
            "materials": "material_cost_minor",
        }.get(key)
        native_value = native_summary.get(native_key) if native_key else None
        uses_native = not isinstance(value, int) and isinstance(native_value, int)
        if uses_native:
            value = native_value
        fact_references = references or [
            item
            for item in native_references
            if item.get("family")
            == ("REVENUE" if key == "revenue" else "DIRECT_MATERIAL")
        ]
        facts.append(
            {
                "family": family,
                "metric": "invoiced_revenue"
                if uses_native and key == "revenue"
                else key,
                "value": value if isinstance(value, int) else None,
                "units": unit,
                "currency": currency,
                "period": period,
                "subject": {
                    "kind": "BRANCH" if branch_id else "COMPANY",
                    "company_id": str(company_id),
                    "branch_id": str(branch_id) if branch_id else None,
                },
                "source": "acp_native" if uses_native else "business_economics",
                "authority": (
                    "accepted_native_invoiced_or_valued_fact"
                    if uses_native
                    else "admitted_immutable_actual_results"
                ),
                "confidence": _confidence(workspace)["score_percent"],
                "prerequisite_completeness": "AVAILABLE"
                if isinstance(value, int)
                else "SOURCE_MISSING",
                "evidence_references": fact_references,
                "as_of": as_of.isoformat(),
            }
        )
    worked_seconds = native_summary.get("accepted_worked_seconds")
    if isinstance(worked_seconds, int):
        facts.append(
            {
                "family": "DIRECT_LABOR",
                "metric": "accepted_worked_seconds",
                "value": worked_seconds,
                "units": "seconds",
                "currency": None,
                "period": period,
                "subject": {
                    "kind": "BRANCH" if branch_id else "COMPANY",
                    "company_id": str(company_id),
                    "branch_id": str(branch_id) if branch_id else None,
                },
                "source": "acp_native_timekeeping",
                "authority": "accepted_authoritative_job_work_intervals",
                "confidence": _confidence(workspace)["score_percent"],
                "prerequisite_completeness": "PARTIAL",
                "evidence_references": [
                    item
                    for item in native_references
                    if item.get("family") == "DIRECT_LABOR"
                ],
                "as_of": as_of.isoformat(),
                "limitations": ["worked duration is not wage cost or paid time"],
            }
        )
    return facts


def _evidence_state(value: object, *, policy_required: bool = False) -> str:
    if value is not None:
        return AnalysisReadiness.READY.value
    return (
        AnalysisReadiness.POLICY_REQUIRED.value
        if policy_required
        else AnalysisReadiness.SOURCE_MISSING.value
    )


def _job_economics(workspace: dict[str, object]) -> list[dict[str, object]]:
    """Compose admitted results with native facts without manufacturing cost."""
    admitted = {str(item.get("job_id")): item for item in _rows(workspace.get("jobs"))}
    native = _mapping(workspace.get("native_evidence"))
    result: list[dict[str, object]] = []
    for job in _rows(native.get("jobs")):
        job_id = str(job.get("job_id"))
        calculated = admitted.get(job_id, {})
        invoice = job.get("invoiced_revenue_minor")
        worked = job.get("accepted_worked_seconds")
        material_usage_count = int(job.get("material_quantity_evidence_count") or 0)
        material_cost = job.get("material_cost_minor")
        direct_wage = calculated.get("labor_minor")
        other_direct = calculated.get("other_direct_cost_minor")
        contribution = calculated.get("contribution_minor")
        references = _rows(job.get("references"))
        conflicts = any(str(item.get("state")) == "CONFLICTING" for item in references)
        missing = []
        if invoice is None:
            missing.append("invoiced_revenue")
        if worked is None:
            missing.append("accepted_job_work")
        if direct_wage is None:
            missing.append("certified_direct_wage_cost")
        if material_usage_count == 0:
            missing.append("actual_material_usage_or_not_applicable_authority")
        elif material_cost is None:
            missing.append("actual_material_valuation")
        if other_direct is None:
            missing.append("other_direct_cost_completeness")
        if contribution is None:
            missing.append("admitted_direct_contribution")
        readiness = (
            AnalysisReadiness.CONFLICTING_EVIDENCE.value
            if conflicts
            else AnalysisReadiness.READY.value
            if not missing
            else AnalysisReadiness.PARTIAL.value
            if invoice is not None or worked is not None or material_usage_count
            else AnalysisReadiness.INSUFFICIENT_EVIDENCE.value
        )
        result.append(
            {
                "job_id": job_id,
                "job_number": job.get("job_number"),
                "job_status": job.get("job_status"),
                "customer": {
                    "id": job.get("customer_id"),
                    "name": job.get("customer_name"),
                },
                "branch": {
                    "id": job.get("branch_id"),
                    "name": job.get("branch_name"),
                },
                "service_category": job.get("service_category"),
                "readiness": readiness,
                "invoiced_revenue_minor": invoice,
                "settlement_applied_minor": job.get("settlement_applied_minor"),
                "accepted_worked_seconds": worked,
                "direct_wage_cost_minor": direct_wage,
                "employer_burden_minor": calculated.get("labor_burden_minor"),
                "material_usage_count": material_usage_count,
                "actual_material_cost_minor": material_cost,
                "other_direct_cost_minor": other_direct,
                "direct_contribution_minor": contribution,
                "contribution_percent_basis_points": (
                    contribution * 10_000 // invoice
                    if isinstance(contribution, int)
                    and isinstance(invoice, int)
                    and invoice != 0
                    else None
                ),
                "fully_loaded_profit_minor": calculated.get("net_profit_minor"),
                "evidence_states": {
                    "revenue": _evidence_state(invoice),
                    "settlement": _evidence_state(job.get("settlement_applied_minor")),
                    "labor_hours": _evidence_state(worked),
                    "direct_wage_cost": _evidence_state(
                        direct_wage, policy_required=worked is not None
                    ),
                    "employer_burden": _evidence_state(
                        calculated.get("labor_burden_minor"), policy_required=True
                    ),
                    "material_usage": _evidence_state(
                        material_usage_count if material_usage_count else None
                    ),
                    "material_valuation": _evidence_state(material_cost),
                    "other_direct_cost": _evidence_state(other_direct),
                    "fully_loaded_profit": _evidence_state(
                        calculated.get("net_profit_minor"), policy_required=True
                    ),
                },
                "missing_prerequisites": missing,
                "confidence_percent": calculated.get("confidence_percent")
                or (70 if readiness == AnalysisReadiness.PARTIAL.value else 80),
                "authority": {
                    "revenue": "ACP_NATIVE_INVOICED",
                    "worked_time": "ACCEPTED_JOB_WORK_INTERVAL",
                    "calculated_cost": "ADMITTED_ECONOMICS_RESULT"
                    if calculated
                    else None,
                },
                "evidence_references": references,
            }
        )
    return sorted(result, key=lambda item: (str(item["job_number"]), item["job_id"]))


def _service_line_economics(
    jobs: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for job in jobs:
        category = job.get("service_category")
        if isinstance(category, str) and category:
            grouped.setdefault(category, []).append(job)
    output = []
    for category, rows in sorted(grouped.items()):
        complete = [item for item in rows if item["readiness"] == "READY"]
        revenue_values = [
            value
            for item in rows
            if isinstance((value := item.get("invoiced_revenue_minor")), int)
        ]
        worked_values = [
            value
            for item in rows
            if isinstance((value := item.get("accepted_worked_seconds")), int)
        ]
        material_values = [
            value
            for item in rows
            if isinstance((value := item.get("actual_material_cost_minor")), int)
        ]
        contribution_values = [
            value
            for item in rows
            if isinstance((value := item.get("direct_contribution_minor")), int)
        ]
        missing_values: set[str] = set()
        for item in rows:
            item_missing = item.get("missing_prerequisites")
            if isinstance(item_missing, list):
                missing_values.update(str(value) for value in item_missing)
        output.append(
            {
                "service_category": category,
                "job_count": len(rows),
                "contribution_ready_job_count": len(complete),
                "invoiced_revenue_minor": sum(revenue_values),
                "accepted_worked_seconds": sum(worked_values),
                "actual_material_cost_minor": (
                    sum(material_values) if len(material_values) == len(rows) else None
                ),
                "direct_contribution_minor": (
                    sum(contribution_values) if len(complete) == len(rows) else None
                ),
                "average_invoiced_ticket_minor": (
                    sum(revenue_values) // len(revenue_values)
                    if revenue_values
                    else None
                ),
                "readiness": "READY" if len(complete) == len(rows) else "PARTIAL",
                "missing_prerequisites": sorted(missing_values),
                "authority": "canonical_job_service_category_rollup",
            }
        )
    return output


def _evidence_priority_queue(
    jobs: list[dict[str, object]],
) -> list[dict[str, object]]:
    affected: dict[str, set[str]] = {}
    for job in jobs:
        missing = job.get("missing_prerequisites")
        if not isinstance(missing, list):
            continue
        for prerequisite in missing:
            affected.setdefault(str(prerequisite), set()).add(str(job["job_id"]))
    ownership = {
        "invoiced_revenue": ("Invoices", "machine_acquirable"),
        "accepted_job_work": ("Timekeeping", "machine_acquirable"),
        "certified_direct_wage_cost": (
            "Payroll/Economics policy",
            "owner_input_required",
        ),
        "actual_material_usage_or_not_applicable_authority": (
            "Inventory/Field Operations",
            "machine_acquirable_or_owner_not_applicable",
        ),
        "actual_material_valuation": (
            "Inventory/Purchasing",
            "accountant_input_required",
        ),
        "other_direct_cost_completeness": (
            "Accounts Payable/Economics",
            "accountant_input_required",
        ),
        "admitted_direct_contribution": (
            "Business Economics",
            "machine_calculated_after_inputs",
        ),
    }
    queue = []
    for prerequisite, job_ids in affected.items():
        owner, next_step = ownership.get(
            prerequisite, ("Source domain", "source_authority_required")
        )
        queue.append(
            {
                "prerequisite": prerequisite,
                "affected_job_count": len(job_ids),
                "affected_job_ids": sorted(job_ids),
                "responsible_domain": owner,
                "next_safe_step": next_step,
                "economic_unlock": (
                    "direct_contribution"
                    if prerequisite != "admitted_direct_contribution"
                    else "owner_profitability_comparison"
                ),
            }
        )
    return sorted(
        queue,
        key=lambda item: (
            -cast(int, item["affected_job_count"]),
            str(item["prerequisite"]),
        ),
    )


def _owner_question_answers(
    jobs: list[dict[str, object]], service_lines: list[dict[str, object]]
) -> dict[str, object]:
    contribution_jobs = [
        item for item in jobs if isinstance(item.get("direct_contribution_minor"), int)
    ]
    ranked = sorted(
        contribution_jobs,
        key=lambda item: cast(int, item["direct_contribution_minor"]),
        reverse=True,
    )
    negative = [
        item for item in ranked if cast(int, item["direct_contribution_minor"]) < 0
    ]
    complete_services = [
        item
        for item in service_lines
        if isinstance(item.get("direct_contribution_minor"), int)
    ]
    return {
        "which_jobs_make_money": {
            "state": "READY" if ranked else "INSUFFICIENT_EVIDENCE",
            "strongest": ranked[:5],
            "weakest": list(reversed(ranked[-5:])),
            "negative": negative,
            "limitation": "Direct contribution only; overhead is not included."
            if ranked
            else "No Job has complete admitted direct-cost and contribution evidence.",
        },
        "which_services_perform_best": {
            "state": "READY" if complete_services else "INSUFFICIENT_EVIDENCE",
            "services": sorted(
                complete_services,
                key=lambda item: cast(int, item["direct_contribution_minor"]),
                reverse=True,
            ),
            "limitation": "Uncategorized and incomplete Jobs are not forced into service-line profit.",
        },
        "what_prevents_fully_loaded_profit": {
            "state": "POLICY_REQUIRED",
            "missing": [
                "complete_direct_contribution",
                "reconciled_overhead_evidence",
                "certified_overhead_pool_membership",
                "certified_overhead_allocation_driver",
            ],
        },
        "causality_boundary": "Measured component differences support investigation; they do not establish cause.",
    }


def _direction(value: int) -> str:
    return "increased" if value > 0 else "decreased" if value < 0 else "did not change"


def _owner_health_snapshot(workspace: dict[str, object]) -> dict[str, object]:
    """Name the four owner-facing measures without creating Economics truth."""
    totals = _mapping(workspace.get("totals"))
    native = _mapping(workspace.get("native_evidence"))
    native_summary = _mapping(native.get("summary"))
    currency = workspace.get("currency") or native_summary.get("currency")

    revenue = totals.get("revenue")
    revenue_authority = "MEASURED"
    revenue_basis = "earned_revenue"
    if not isinstance(revenue, int):
        revenue = native_summary.get("invoiced_revenue_minor")
        revenue_authority = (
            "AUTHORITATIVE" if isinstance(revenue, int) else "UNAVAILABLE"
        )
        revenue_basis = (
            "invoiced_revenue" if isinstance(revenue, int) else "unavailable"
        )

    contribution = totals.get("gross_profit")
    contribution_available = isinstance(contribution, int)
    burden = totals.get("overhead")
    burden_available = workspace.get(
        "fully_allocated_available"
    ) is True and isinstance(burden, int)
    health_basis_points = None
    if contribution_available and burden_available and cast(int, burden) > 0:
        health_basis_points = cast(int, contribution) * 10_000 // cast(int, burden)

    readiness = _mapping(workspace.get("readiness"))
    allocation = _mapping(readiness.get("allocation_authority"))
    missing_burden = (
        []
        if burden_available
        else [
            "field_capacity_burden",
            "office_and_administration",
            "owner_compensation",
            "trucks_and_fixed_costs",
            "rent_and_utilities",
            "insurance_software_and_professional",
            "marketing",
            "other_admitted_fixed_or_semi_fixed_burden",
        ]
    )
    return {
        "revenue_production": {
            "value_minor": revenue if isinstance(revenue, int) else None,
            "classification": revenue_authority,
            "basis": revenue_basis,
            "currency": currency,
            "limitation": (
                "Accepted invoiced revenue is shown; it is not earned revenue or collected cash."
                if revenue_basis == "invoiced_revenue"
                else None
            ),
        },
        "economic_contribution": {
            "value_minor": contribution if contribution_available else None,
            "classification": "MEASURED" if contribution_available else "UNAVAILABLE",
            "currency": currency,
            "formula": "revenue minus admitted job-variable costs",
            "limitation": None
            if contribution_available
            else "Complete admitted direct costs are required.",
        },
        "required_economic_burden": {
            "value_minor": burden if burden_available else None,
            "classification": "AUTHORITATIVE" if burden_available else "UNAVAILABLE",
            "currency": currency,
            "missing_components": missing_burden,
            "policy_state": allocation.get("state")
            or readiness.get("allocation_policy")
            or "policy_required",
            "limitation": None
            if burden_available
            else "ACP has not admitted a complete approved burden pool and allocation for this period.",
        },
        "economic_health": {
            "value_basis_points": health_basis_points,
            "classification": "MEASURED"
            if health_basis_points is not None
            else "UNAVAILABLE",
            "break_even_basis_points": 10_000,
            "status": (
                "ABOVE_BREAK_EVEN"
                if health_basis_points is not None and health_basis_points > 10_000
                else "AT_BREAK_EVEN"
                if health_basis_points == 10_000
                else "BELOW_BREAK_EVEN"
                if health_basis_points is not None
                else "UNAVAILABLE"
            ),
            "formula": "economic contribution divided by required economic burden",
            "limitation": None
            if health_basis_points is not None
            else "Economic Health remains unknown until both contribution and required burden are authoritative for the same period.",
        },
        "cash_health": {
            "classification": "UNAVAILABLE",
            "separate_from_economic_health": True,
            "limitation": "Cash Health is a separate Accounting authority and is not inferred here.",
        },
    }


_GAP_GUIDANCE: Final[dict[str, dict[str, str]]] = {
    "invoiced_revenue": {
        "why": "Revenue Production cannot be established for the affected Jobs.",
        "source": "Invoices",
        "party": "SYSTEM",
        "path": "/invoices",
        "path_label": "Invoices",
        "unlocks": "authoritative invoiced Revenue Production",
    },
    "accepted_job_work": {
        "why": "Job labor duration and the basis for direct labor cost remain incomplete.",
        "source": "Timekeeping",
        "party": "OWNER",
        "path": "/employees",
        "path_label": "Employees & Time -> Time & Attendance",
        "unlocks": "accepted Job work and downstream labor-cost evidence",
    },
    "certified_direct_wage_cost": {
        "why": "Economic Contribution cannot subtract authoritative Job-variable labor cost.",
        "source": "Payroll / Business Economics",
        "party": "OWNER",
        "path": "/payroll",
        "path_label": "Payroll -> First real Payroll readiness",
        "unlocks": "direct labor cost and Job Economic Contribution",
    },
    "actual_material_usage_or_not_applicable_authority": {
        "why": "ACP cannot tell whether material cost is absent or merely unrecorded for affected Jobs.",
        "source": "Inventory / Field Operations",
        "party": "OWNER",
        "path": "/inventory",
        "path_label": "Inventory -> Job material evidence",
        "unlocks": "material completeness for Job contribution",
    },
    "actual_material_valuation": {
        "why": "Used materials cannot be valued as authoritative Job-variable cost.",
        "source": "Inventory / Purchasing / Accounting",
        "party": "ACCOUNTANT",
        "path": "/purchasing",
        "path_label": "Purchasing -> Material and receipt review",
        "unlocks": "actual material cost and stronger Job contribution",
    },
    "other_direct_cost_completeness": {
        "why": "Merchant fees, subcontractors, permits, disposal, rentals, or other direct Job costs may be incomplete.",
        "source": "Accounts Payable / Business Economics",
        "party": "ACCOUNTANT",
        "path": "/accounts-payable",
        "path_label": "Accounts Payable -> Vendor obligation review",
        "unlocks": "complete other direct cost and Job contribution",
    },
    "admitted_direct_contribution": {
        "why": "All source inputs may exist, but an admitted immutable Economics result is not available.",
        "source": "Business Economics",
        "party": "SYSTEM",
        "path": "/business-economics",
        "path_label": "Business Economics -> Evidence workspace",
        "unlocks": "measured Economic Contribution",
    },
    "field_capacity_burden": {
        "why": "Every break-even comparison needs admitted field capacity and employer burden.",
        "source": "Payroll / Workforce",
        "party": "ACCOUNTANT",
        "path": "/payroll",
        "path_label": "Payroll -> First real Payroll readiness",
        "unlocks": "field capacity burden within Required Economic Burden",
    },
    "office_and_administration": {
        "why": "Required Economic Burden cannot include office and administrative capacity yet.",
        "source": "Payroll / Accounting",
        "party": "OWNER",
        "path": "/business-economics/administration",
        "path_label": "Business Economics -> Policy administration",
        "unlocks": "office and administrative burden",
    },
    "owner_compensation": {
        "why": "Break-even would be understated without the owner's approved compensation burden.",
        "source": "Payroll / Business Economics policy",
        "party": "OWNER",
        "path": "/business-economics/administration",
        "path_label": "Business Economics -> Policy administration",
        "unlocks": "owner compensation within Required Economic Burden",
    },
    "trucks_and_fixed_costs": {
        "why": "Required field fleet and fixed operating cost are not admitted for this period.",
        "source": "Assets / Accounting",
        "party": "OWNER",
        "path": "/assets",
        "path_label": "Assets -> Fleet evidence",
        "unlocks": "truck and fixed field burden",
    },
    "rent_and_utilities": {
        "why": "Occupancy burden is absent from the authoritative break-even denominator.",
        "source": "Accounts Payable / Accounting",
        "party": "ACCOUNTANT",
        "path": "/accounts-payable",
        "path_label": "Accounts Payable -> Vendor obligation review",
        "unlocks": "rent and utility burden",
    },
    "insurance_software_and_professional": {
        "why": "Recurring insurance, software, and professional burden is not complete.",
        "source": "Accounts Payable / Accounting",
        "party": "ACCOUNTANT",
        "path": "/accounts-payable",
        "path_label": "Accounts Payable -> Vendor obligation review",
        "unlocks": "recurring insurance, software, and professional burden",
    },
    "marketing": {
        "why": "Economic Health cannot include authoritative marketing burden yet.",
        "source": "Marketing Economics / Accounting",
        "party": "PROVIDER",
        "path": "",
        "path_label": "Unavailable — no authoritative Marketing input route",
        "unlocks": "marketing burden and service-acquisition context",
    },
    "other_admitted_fixed_or_semi_fixed_burden": {
        "why": "Other approved fixed or semi-fixed obligations may still be outside the burden pool.",
        "source": "Accounting / Business Economics policy",
        "party": "ACCOUNTANT",
        "path": "/business-economics/administration",
        "path_label": "Business Economics -> Policy administration",
        "unlocks": "complete Required Economic Burden",
    },
}


def _active_economic_reasoning(
    workspace: dict[str, object],
    jobs: list[dict[str, object]],
    owner_health: dict[str, object],
    job_queue: list[dict[str, object]],
) -> dict[str, object]:
    """Interpret admitted completeness without estimating any missing value."""
    health_contribution = _mapping(owner_health.get("economic_contribution"))
    health_burden = _mapping(owner_health.get("required_economic_burden"))
    health = _mapping(owner_health.get("economic_health"))
    admitted_results = _rows(workspace.get("jobs"))
    ready_jobs = sum(
        isinstance(item.get("contribution_minor"), int) for item in admitted_results
    )
    job_count = max(len(jobs), len(admitted_results))
    contribution_coverage = ready_jobs * 10_000 // job_count if job_count else 0
    contribution_state = (
        "AUTHORITATIVE"
        if job_count and ready_jobs == job_count
        else "PARTIAL"
        if ready_jobs
        else "UNAVAILABLE"
    )

    candidates: list[dict[str, object]] = []
    for item in job_queue:
        gap = str(item.get("prerequisite"))
        guidance = _GAP_GUIDANCE.get(gap)
        if guidance is None:
            continue
        affected_job_count = item.get("affected_job_count")
        candidates.append(
            {
                "gap": gap,
                "evidence_state": "UNAVAILABLE",
                "decision_impact": (
                    "BLOCKS_CONTRIBUTION_AND_HEALTH"
                    if gap != "admitted_direct_contribution"
                    else "BLOCKS_MEASURED_CONTRIBUTION"
                ),
                "priority_tier": 1 if gap != "admitted_direct_contribution" else 2,
                "affected_job_count": affected_job_count
                if isinstance(affected_job_count, int)
                else 0,
                "affected_calculations": ["ECONOMIC_CONTRIBUTION", "ECONOMIC_HEALTH"],
                "expected_source": guidance["source"],
                "responsible_party": guidance["party"],
                "ui_path": guidance["path"],
                "ui_path_label": guidance["path_label"],
                "why_it_matters": guidance["why"],
                "unlocks": guidance["unlocks"],
            }
        )
    missing_burden = health_burden.get("missing_components")
    if isinstance(missing_burden, list):
        for raw_gap in missing_burden:
            gap = str(raw_gap)
            guidance = _GAP_GUIDANCE.get(gap)
            if guidance is None:
                continue
            candidates.append(
                {
                    "gap": gap,
                    "evidence_state": "UNAVAILABLE",
                    "decision_impact": "BLOCKS_AUTHORITATIVE_BREAK_EVEN",
                    "priority_tier": 3,
                    "affected_job_count": None,
                    "affected_calculations": [
                        "REQUIRED_ECONOMIC_BURDEN",
                        "ECONOMIC_HEALTH",
                    ],
                    "expected_source": guidance["source"],
                    "responsible_party": guidance["party"],
                    "ui_path": guidance["path"],
                    "ui_path_label": guidance["path_label"],
                    "why_it_matters": guidance["why"],
                    "unlocks": guidance["unlocks"],
                }
            )
    ordered = sorted(
        candidates,
        key=lambda item: (
            cast(int, item["priority_tier"]),
            -cast(int, item["affected_job_count"] or 0),
            str(item["gap"]),
        ),
    )
    for index, item in enumerate(ordered, start=1):
        item["rank"] = index

    can_conclude = ["Revenue Production at its explicitly labeled authority and basis."]
    if contribution_state == "AUTHORITATIVE":
        can_conclude.append(
            "Economic Contribution for the complete admitted Job population."
        )
    elif contribution_state == "PARTIAL":
        can_conclude.append(
            "Economic Contribution for only the Jobs with complete admitted variable costs."
        )
    if health.get("value_basis_points") is not None:
        can_conclude.append("Economic Health against the approved same-period burden.")
    cannot_conclude = []
    if contribution_state != "AUTHORITATIVE":
        cannot_conclude.append("Company-wide Economic Contribution remains incomplete.")
    if health.get("value_basis_points") is None:
        cannot_conclude.append(
            "ACP cannot state whether the business is above or below break-even."
        )
    cannot_conclude.append(
        "Observed component movement does not prove an operational cause."
    )
    return {
        "contribution": {
            "state": contribution_state,
            "value_minor": health_contribution.get("value_minor")
            if contribution_state == "AUTHORITATIVE"
            else None,
            "job_population_coverage_basis_points": contribution_coverage,
            "coverage_basis": "jobs_with_complete_admitted_variable_costs",
            "ready_job_count": ready_jobs,
            "job_count": job_count,
        },
        "required_burden": {
            "state": health_burden.get("classification", "UNAVAILABLE"),
            "value_minor": health_burden.get("value_minor"),
            "coverage_basis_points": None,
            "coverage_limitation": "Category coverage is not converted to a percentage without category-level authoritative values.",
        },
        "economic_health": {
            "state": health.get("classification", "UNAVAILABLE"),
            "status": health.get("status", "UNAVAILABLE"),
            "value_basis_points": health.get("value_basis_points"),
        },
        "can_conclude": can_conclude,
        "cannot_conclude": cannot_conclude,
        "ranked_evidence_gaps": ordered,
        "highest_value_next_action": ordered[0] if ordered else None,
        "ranking_basis": "Decision dependency first, then affected authoritative Job population; missing values are never estimated.",
        "causality_semantics": {
            "observed_change": "authoritative equal-period component difference",
            "interpretation": "arithmetic effect on contribution when complete",
            "possible_driver": "a measured component worth investigating",
            "unproven_cause": "no causal conclusion without owning-domain evidence",
        },
    }


def _delta_explanation(
    workspace: dict[str, object],
    *,
    company_id: UUID,
    branch_id: UUID | None,
    generated_at: datetime,
) -> dict[str, object]:
    period = _mapping(workspace.get("period"))
    prior_period = _mapping(workspace.get("prior_period"))
    comparison = _mapping(workspace.get("comparison"))
    native_comparison = _mapping(workspace.get("native_evidence_comparison"))
    scope = {
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
    }
    common = {
        "period": period,
        "prior_period": prior_period or None,
        "scope": scope,
        "as_of": generated_at.isoformat(),
        "freshness": str(workspace.get("quality_state", "unavailable")),
        "currency": workspace.get("currency"),
        "causality_boundary": "Arithmetic decomposition identifies measured contributors, not operational cause.",
    }
    if comparison.get("state") == "available":
        keys = (
            ("revenue", "revenue_change_minor", 1),
            ("direct_labor_cost", "labor_change_minor", -1),
            ("direct_material_cost", "materials_change_minor", -1),
            ("other_direct_cost", "other_direct_cost_change_minor", -1),
        )
        if not all(isinstance(comparison.get(key), int) for _, key, _ in keys):
            return {
                **common,
                "state": "INCOMPLETE",
                "reason": "Comparable periods lack a complete admitted component decomposition.",
                "components": [],
                "unexplained_change_minor": None,
            }
        contribution = comparison.get("contribution_change_minor")
        if not isinstance(contribution, int):
            return {
                **common,
                "state": "INCOMPLETE",
                "reason": "Comparable periods lack admitted contribution evidence.",
                "components": [],
                "unexplained_change_minor": None,
            }
        components = [
            {
                "component": name,
                "change_minor": cast(int, comparison[key]),
                "contribution_effect_minor": cast(int, comparison[key]) * sign,
                "classification": "DETERMINISTIC_DERIVED_CALCULATION",
                "authority": "admitted_immutable_economics_results",
            }
            for name, key, sign in keys
        ]
        explained = sum(
            cast(int, item["contribution_effect_minor"]) for item in components
        )
        current = _mapping(comparison.get("current"))
        prior = _mapping(comparison.get("prior"))
        contribution_margin_change_basis_points = None
        if (
            all(
                isinstance(value, int)
                for value in (
                    current.get("revenue_minor"),
                    current.get("contribution_minor"),
                    prior.get("revenue_minor"),
                    prior.get("contribution_minor"),
                )
            )
            and cast(int, current["revenue_minor"])
            and cast(int, prior["revenue_minor"])
        ):
            contribution_margin_change_basis_points = cast(
                int, current["contribution_minor"]
            ) * 10_000 // cast(int, current["revenue_minor"]) - cast(
                int, prior["contribution_minor"]
            ) * 10_000 // cast(int, prior["revenue_minor"])
        return {
            **common,
            "state": "EXPLAINED" if explained == contribution else "INCOMPLETE",
            "authority": "equal_length_admitted_economics_results",
            "classification": "DETERMINISTIC_DERIVED_CALCULATION",
            "headline": (
                f"Contribution {_direction(contribution)} by {abs(contribution)} minor currency units."
            ),
            "explanation": "The contribution change is the arithmetic effect of measured revenue and admitted direct-cost changes; it does not establish an operational cause.",
            "contribution_change_minor": contribution,
            "contribution_margin_change_basis_points": contribution_margin_change_basis_points,
            "components": components,
            "explained_change_minor": explained,
            "unexplained_change_minor": contribution - explained,
            "evidence_references": comparison.get("evidence_references", {}),
            "missing_evidence": [],
        }
    if native_comparison.get("state") == "AVAILABLE":
        revenue_change = native_comparison.get("invoiced_revenue_change_minor")
        return {
            **common,
            "state": "PARTIAL",
            "authority": "accepted_native_invoiced_evidence",
            "classification": "MEASURED_PERIOD_DIFFERENCE",
            "headline": (
                f"Invoiced revenue {_direction(revenue_change)} by {abs(revenue_change)} minor currency units."
                if isinstance(revenue_change, int)
                else "Invoiced revenue comparison is incomplete."
            ),
            "explanation": "ACP can measure invoiced revenue change but cannot explain contribution change without admitted direct costs.",
            "components": (
                [
                    {
                        "component": "invoiced_revenue",
                        "change_minor": revenue_change,
                        "contribution_effect_minor": None,
                        "classification": "MEASURED_PERIOD_DIFFERENCE",
                        "authority": "accepted_native_invoiced_evidence",
                    }
                ]
                if isinstance(revenue_change, int)
                else []
            ),
            "unexplained_change_minor": None,
            "missing_evidence": [
                "admitted_direct_labor_cost",
                "admitted_direct_material_cost",
                "other_direct_cost_completeness",
                "admitted_direct_contribution",
            ],
        }
    quality = str(workspace.get("quality_state", "unavailable"))
    return {
        **common,
        "state": "CONFLICTING" if quality == "conflicting" else "NOT_COMPARABLE",
        "reason": comparison.get("reason")
        or "Equal-length periods do not both contain comparable admitted evidence.",
        "components": [],
        "unexplained_change_minor": None,
        "missing_evidence": ["comparable_period_evidence"],
    }


def _recommendations(
    workspace: dict[str, object],
    *,
    company_id: UUID,
    period: dict[str, Any],
    generated_at: datetime,
) -> list[dict[str, object]]:
    if _readiness(workspace) is not AnalysisReadiness.READY:
        return []
    jobs = _rows(workspace.get("jobs"))
    confidence_value = _confidence(workspace)["score_percent"]
    confidence = confidence_value if isinstance(confidence_value, int) else 0
    result: list[dict[str, object]] = []
    for job in jobs:
        contribution = job.get("contribution_minor")
        if not isinstance(contribution, int) or contribution >= 0:
            continue
        payload = {
            "family": RecommendationFamily.PRICING.value,
            "subject": {
                "kind": "JOB",
                "id": str(job.get("job_id")),
                "label": str(job.get("job_number")),
            },
            "period": period,
            "baseline": {
                "contribution_minor": contribution,
                "revenue_minor": job.get("revenue_minor"),
            },
            "evidence_references": [
                {"record_id": job.get("result_id"), "digest": job.get("result_digest")}
            ],
            "economic_mechanism": "Measured Job contribution is below zero; inspect price and admitted direct-cost components without presuming cause.",
        }
        digest = _digest(payload)
        result.append(
            {
                "recommendation_id": str(uuid5(_NAMESPACE, digest)),
                **payload,
                "measured_facts": [
                    "revenue",
                    "labor",
                    "materials",
                    "other_direct_cost",
                    "contribution",
                ],
                "confidence": confidence,
                "expected_direction_of_impact": "review_could_identify_margin_leakage",
                "estimated_range": None,
                "assumptions": [],
                "uncertainty": [
                    "negative contribution does not establish underpricing"
                ],
                "contraindications": [
                    "do not change price without approved policy and service-level evidence"
                ],
                "missing_evidence": list(job.get("missing_categories") or []),
                "alternatives": [
                    "inspect labor variance",
                    "inspect material consumption",
                    "inspect Job scope and service mix",
                ],
                "owner_decision_required": "Decide whether to investigate this Job or related Price Book item.",
                "status": "CANDIDATE_READ_ONLY",
                "version": CONTRACT_VERSION,
                "supersedes": None,
                "generated_at": generated_at.isoformat(),
            }
        )
    return result[:10]


def _scenario(
    workspace: dict[str, object], assumption: ScenarioAssumption | None
) -> dict[str, object] | None:
    if assumption is None:
        return None
    totals = _mapping(workspace.get("totals"))
    baseline = {
        key: totals.get(key)
        for key in ("revenue", "labor", "materials", "gross_profit")
    }
    if assumption.kind in {ScenarioKind.CLOSE_RATE_PERCENT, ScenarioKind.ADD_TRUCK}:
        blocker = (
            "authoritative_conversion_population"
            if assumption.kind is ScenarioKind.CLOSE_RATE_PERCENT
            else "fleet_constrained_capacity_and_incremental_cost"
        )
        return {
            "state": AnalysisReadiness.INSUFFICIENT_EVIDENCE.value,
            "baseline": baseline,
            "changed_assumption": asdict(assumption),
            "missing_prerequisites": [blocker],
            "hypothetical": True,
            "operational_action_occurred": False,
        }
    if _readiness(workspace) is not AnalysisReadiness.READY or any(
        not isinstance(value, int) for value in baseline.values()
    ):
        return {
            "state": AnalysisReadiness.INSUFFICIENT_EVIDENCE.value,
            "baseline": baseline,
            "changed_assumption": asdict(assumption),
            "missing_prerequisites": [
                "complete_admitted_revenue_labor_material_and_contribution"
            ],
            "hypothetical": True,
            "operational_action_occurred": False,
        }
    change = int(assumption.change_basis_points or 0)
    baseline_values = {
        key: value for key, value in baseline.items() if isinstance(value, int)
    }
    scenario = {
        key: int(value) for key, value in baseline.items() if isinstance(value, int)
    }
    if assumption.kind in {
        ScenarioKind.PRICE_PERCENT,
        ScenarioKind.AVERAGE_TICKET_PERCENT,
    }:
        scenario["revenue"] += scenario["revenue"] * change // 10_000
    elif assumption.kind is ScenarioKind.LABOR_EFFICIENCY_PERCENT:
        scenario["labor"] -= scenario["labor"] * change // 10_000
    elif assumption.kind is ScenarioKind.MATERIAL_COST_PERCENT:
        scenario["materials"] += scenario["materials"] * change // 10_000
    scenario["gross_profit"] = (
        scenario["revenue"]
        - scenario["labor"]
        - scenario["materials"]
        - (
            baseline_values["revenue"]
            - baseline_values["labor"]
            - baseline_values["materials"]
            - baseline_values["gross_profit"]
        )
    )
    return {
        "state": AnalysisReadiness.READY.value,
        "baseline": baseline,
        "changed_assumption": asdict(assumption),
        "unchanged_assumptions": [
            "all admitted baseline components not explicitly changed"
        ],
        "output_metrics": scenario,
        "deltas": {key: scenario[key] - baseline_values[key] for key in scenario},
        "confidence": _confidence(workspace),
        "missing_prerequisites": [],
        "sensitivity": "single_assumption_linear_arithmetic",
        "break_even_threshold": None,
        "hypothetical": True,
        "authoritative_actual": False,
        "operational_action_occurred": False,
    }


def project_owner_economics(
    workspace: dict[str, object],
    *,
    company_id: UUID,
    branch_id: UUID | None,
    generated_at: datetime,
    scenario: ScenarioAssumption | None = None,
) -> dict[str, object]:
    """Return a read-only decision-support packet; no object is persisted."""
    period = _mapping(workspace.get("period"))
    readiness = _readiness(workspace)
    completeness = source_completeness_matrix(workspace)
    recommendations = _recommendations(
        workspace, company_id=company_id, period=period, generated_at=generated_at
    )
    facts = _facts(
        workspace, company_id=company_id, branch_id=branch_id, as_of=generated_at
    )
    job_economics = _job_economics(workspace)
    service_line_economics = _service_line_economics(job_economics)
    owner_health = _owner_health_snapshot(workspace)
    evidence_priority_queue = _evidence_priority_queue(job_economics)
    packet: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "engine_version": ENGINE_VERSION,
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "period": period,
        "prior_period": workspace.get("prior_period"),
        "currency": workspace.get("currency"),
        "readiness": readiness.value,
        "facts": facts,
        "job_economics": job_economics,
        "service_line_economics": service_line_economics,
        "owner_health": owner_health,
        "active_reasoning": _active_economic_reasoning(
            workspace,
            job_economics,
            owner_health,
            evidence_priority_queue,
        ),
        "evidence_priority_queue": evidence_priority_queue,
        "owner_question_answers": _owner_question_answers(
            job_economics, service_line_economics
        ),
        "admitted_source_evidence": workspace.get("native_evidence"),
        "confidence": _confidence(workspace),
        "recommendation_candidates": recommendations,
        "scenario": _scenario(workspace, scenario),
        "decision_packets": [
            {
                "decision_question": item["owner_decision_required"],
                "current_measured_state": item["baseline"],
                "economic_impact": item["expected_direction_of_impact"],
                "evidence": item["evidence_references"],
                "confidence": item["confidence"],
                "alternatives": item["alternatives"],
                "risks": item["contraindications"],
                "missing_evidence": item["missing_evidence"],
                "scenario_comparisons": [],
                "recommended_human_review": True,
                "actions_requiring_owner_approval": [
                    "any pricing, staffing, purchasing, or policy change"
                ],
            }
            for item in recommendations
        ],
        "explanation_boundary": {
            "measured_fact": "facts and admitted period comparisons",
            "correlation": "co-movement may be reported but does not establish cause",
            "plausible_causes": [
                "price",
                "labor",
                "material",
                "other direct cost",
                "service mix",
                "missing evidence",
            ],
            "recommendation": "candidate for human investigation only",
            "what_would_distinguish_alternatives": "component-level authoritative evidence for the same Job, scope, and period",
        },
        "source_readiness": completeness,
        "trend_support": {
            "state": "READY"
            if _mapping(workspace.get("comparison")).get("state") == "available"
            or _mapping(workspace.get("native_evidence_comparison")).get("state")
            == "AVAILABLE"
            else "INSUFFICIENT_EVIDENCE",
            "comparison": (
                workspace.get("comparison")
                if _mapping(workspace.get("comparison")).get("state") == "available"
                else workspace.get("native_evidence_comparison")
            ),
            "authority": "equal_length_single_authority_periods_only",
            "mixed_authority_periods": "labeled_and_not_combined",
        },
        "delta_explanation": _delta_explanation(
            workspace,
            company_id=company_id,
            branch_id=branch_id,
            generated_at=generated_at,
        ),
        "market_evidence": {
            "state": "INSUFFICIENT_MARKET_EVIDENCE",
            "reason": "no admitted competitive or market-price evidence",
        },
        "unsupported_questions": [
            "competitor or market price without admitted market evidence",
            "customer lifetime value without sufficient longitudinal evidence",
            "close-rate scenarios without authoritative opportunity conversion populations",
            "truck-capacity scenarios without Fleet-constrained capacity and incremental-cost evidence",
            "fully loaded profit or break-even without approved allocation and policy prerequisites",
            "Employee causality, ranking, discipline, compensation, or termination conclusions",
        ],
        "workforce_boundary": "aggregate or Job-attributed admitted labor only; no ranking, compensation exposure, or employment action",
        "beacon_boundary": "references existing conditions only; Beacon retains lifecycle ownership",
        "lia_boundary": "Luminary owns economics truth; LIA may present this packet conversationally and cannot mutate it",
        "mutation_authority": "none",
        "generated_at": generated_at.isoformat(),
    }
    packet["packet_digest"] = _digest(packet)
    return packet
