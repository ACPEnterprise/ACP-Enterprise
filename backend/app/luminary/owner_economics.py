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
    packet: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "engine_version": ENGINE_VERSION,
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "period": period,
        "prior_period": workspace.get("prior_period"),
        "readiness": readiness.value,
        "facts": facts,
        "job_economics": job_economics,
        "service_line_economics": service_line_economics,
        "evidence_priority_queue": _evidence_priority_queue(job_economics),
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
