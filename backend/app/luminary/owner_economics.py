"""Pure, deterministic owner Economics intelligence over admitted projections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Final
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
        return AnalysisReadiness.SOURCE_MISSING
    if quality in {"partial", "stale"}:
        return AnalysisReadiness.PARTIAL
    return AnalysisReadiness.READY


def _confidence(workspace: dict[str, object]) -> dict[str, object]:
    jobs = _rows(workspace.get("jobs"))
    scores = [int(item.get("confidence_percent") or 0) for item in jobs]
    completeness = str(workspace.get("quality_state", "unavailable"))
    score = min(scores) if scores else 0
    if completeness == "partial":
        score = min(score, 70)
    elif completeness == "stale":
        score = min(score, 50)
    elif completeness in {"conflicting", "unavailable"}:
        score = 0
    return {
        "score_percent": score,
        "method": "minimum_admitted_job_confidence_with_quality_caps",
        "factors": {
            "source_authority": "admitted_business_economics_only",
            "completeness": completeness,
            "recency": "current" if completeness == "complete" else completeness,
            "reconciliation": "conflicting"
            if completeness == "conflicting"
            else "preserved",
            "sample_size": len(jobs),
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
    references = [
        {
            "record_type": "profitability_result",
            "record_id": str(item.get("result_id")),
            "digest": str(item.get("result_digest")),
        }
        for item in jobs
        if item.get("result_id") and item.get("result_digest")
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
        facts.append(
            {
                "family": family,
                "metric": key,
                "value": value if isinstance(value, int) else None,
                "units": unit,
                "currency": currency,
                "period": period,
                "subject": {
                    "kind": "BRANCH" if branch_id else "COMPANY",
                    "company_id": str(company_id),
                    "branch_id": str(branch_id) if branch_id else None,
                },
                "source": "business_economics",
                "authority": "admitted_immutable_actual_results",
                "confidence": _confidence(workspace)["score_percent"],
                "prerequisite_completeness": "AVAILABLE"
                if isinstance(value, int)
                else "SOURCE_MISSING",
                "evidence_references": references,
                "as_of": as_of.isoformat(),
            }
        )
    return facts


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
    packet: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "engine_version": ENGINE_VERSION,
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "period": period,
        "readiness": readiness.value,
        "facts": facts,
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
            else "INSUFFICIENT_EVIDENCE",
            "comparison": workspace.get("comparison"),
            "authority": "equal_length_admitted_actual_periods_only",
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
