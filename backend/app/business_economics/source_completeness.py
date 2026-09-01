"""Deterministic source readiness for owner profitability interpretation.

The matrix describes accepted Economics result evidence.  It never promotes a
domain record into an economic fact and never turns missing evidence into zero.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

SOURCE_COMPLETENESS_VERSION = "economics.source-completeness.v1"


class SourceCompletenessState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    POLICY_REQUIRED = "POLICY_REQUIRED"
    SOURCE_REQUIRED = "SOURCE_REQUIRED"
    EXTERNAL_GATE = "EXTERNAL_GATE"
    UNAVAILABLE = "UNAVAILABLE"


def source_completeness_matrix(workspace: dict[str, object]) -> dict[str, object]:
    quality = str(workspace.get("quality_state") or "unavailable")
    base = {
        "complete": SourceCompletenessState.AVAILABLE,
        "partial": SourceCompletenessState.PARTIAL,
        "stale": SourceCompletenessState.STALE,
        "conflicting": SourceCompletenessState.CONFLICTING,
        "unavailable": SourceCompletenessState.UNAVAILABLE,
    }.get(quality, SourceCompletenessState.UNAVAILABLE)
    jobs = _rows(workspace.get("jobs"))
    totals = _mapping(workspace.get("totals"))
    readiness = _mapping(workspace.get("readiness"))
    source_count = _count(workspace.get("source_result_count"))

    sources = (
        _entry(
            "revenue",
            _component_state(base, totals, "revenue"),
            source_count,
            "Accepted earned-revenue evidence in admitted Job profitability results.",
        ),
        _entry(
            "settlement",
            SourceCompletenessState.POLICY_REQUIRED,
            0,
            "Settlement is distinct from earned revenue; a cash-recognition policy and admitted settlement measurement are required.",
        ),
        _entry(
            "direct_labor",
            _component_state(base, totals, "labor"),
            source_count,
            "Direct labor is accepted only through admitted Economics measurement lineage.",
        ),
        _entry(
            "employer_burden",
            SourceCompletenessState.PARTIAL
            if totals.get("labor") is not None
            else SourceCompletenessState.UNAVAILABLE,
            source_count,
            "Labor may include admitted Payroll provenance, but independently explainable employer-burden composition is not represented in this result projection.",
        ),
        _entry(
            "materials",
            _component_state(base, totals, "materials"),
            source_count,
            "Direct materials are accepted only through admitted Economics measurement lineage.",
        ),
        _entry(
            "other_direct_cost",
            _other_cost_state(base, jobs),
            source_count,
            "Other direct cost is limited to explicit equipment/truck components; no additional cost is inferred.",
        ),
        _entry(
            "overhead_allocation",
            _allocation_state(base, workspace),
            source_count,
            "Fully allocated profitability requires explicit approved allocation authority.",
        ),
        _entry(
            "job_identity_lifecycle",
            _identity_state(base, workspace),
            len(jobs),
            "Job identity and lifecycle must reconcile to authoritative Company and Branch records.",
        ),
        _entry(
            "service_category",
            _category_state(base, workspace),
            len(jobs),
            "Service/category rollups require canonical Job classification; free text is not classified.",
        ),
        _entry(
            "customer_attribution",
            _rollup_state(base, workspace, "customers"),
            len(_rows(workspace.get("customers"))),
            "Customer economics uses authoritative Customer-to-Job identity; it does not infer lifetime value.",
        ),
        _entry(
            "branch_attribution",
            _rollup_state(base, workspace, "branches"),
            len(_rows(workspace.get("branches"))),
            "Branch economics requires authoritative Job Branch identity and compatible periods, policy, and currency.",
        ),
        _entry(
            "workforce_attribution",
            SourceCompletenessState.PARTIAL
            if totals.get("labor") is not None
            else SourceCompletenessState.SOURCE_REQUIRED,
            source_count,
            "Aggregate labor may be admitted, but Employee-to-Job economics requires explicit protected attribution authority.",
        ),
        _entry(
            "procurement_inventory_provenance",
            SourceCompletenessState.PARTIAL
            if totals.get("materials") is not None
            else SourceCompletenessState.SOURCE_REQUIRED,
            source_count,
            "Material totals require accepted Job-cost evidence; purchase or receipt evidence alone is not Accounting expense.",
        ),
        _entry(
            "callback_warranty_relationship",
            SourceCompletenessState.EXTERNAL_GATE,
            0,
            "Callback/warranty economics requires an authoritative corrective-work relationship from Jobs/Assets.",
        ),
        _entry(
            "service_agreement_economics",
            SourceCompletenessState.SOURCE_REQUIRED,
            0,
            "Enrollment and billing readiness are not recognized revenue; admitted financial and service-consumption evidence is required.",
        ),
        _entry(
            "capacity_utilization",
            SourceCompletenessState.SOURCE_REQUIRED,
            0,
            "Capacity economics requires accepted capacity, schedule, completion, and labor measurement contracts without an invented target.",
        ),
        _entry(
            "cash_working_capital",
            SourceCompletenessState.EXTERNAL_GATE,
            0,
            "Cash and working capital require admitted native Accounting evidence; Payments or partial Migration evidence are insufficient.",
        ),
        _entry(
            "accounting_evidence",
            _accounting_state(base, readiness),
            source_count,
            "Accounting remains a separate authority; only admitted reconciliation lineage may support Economics.",
        ),
    )
    canonical = {
        "version": SOURCE_COMPLETENESS_VERSION,
        "period": workspace.get("period"),
        "quality_state": quality,
        "sources": sources,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **canonical,
        "matrix_digest": digest,
        "complete_for_direct_contribution": all(
            item["state"] == SourceCompletenessState.AVAILABLE
            for item in sources
            if item["source"]
            in {"revenue", "direct_labor", "materials", "job_identity_lifecycle"}
        ),
        "complete_for_fully_allocated_profitability": all(
            item["state"] == SourceCompletenessState.AVAILABLE
            for item in sources
            if item["source"]
            in {
                "revenue",
                "direct_labor",
                "materials",
                "other_direct_cost",
                "overhead_allocation",
                "job_identity_lifecycle",
            }
        ),
        "limitations": (
            "Source readiness does not select recognition or allocation policy.",
            "Missing evidence is never interpreted as a zero amount.",
            "Settlement and Accounting truth remain owned by their authoritative domains.",
        ),
        "exceptions": economic_exception_center(sources),
    }


def economic_exception_center(
    sources: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    """Bounded read-only exceptions; ownership and mutation stay in source domains."""
    priority = {
        SourceCompletenessState.CONFLICTING: 0,
        SourceCompletenessState.STALE: 1,
        SourceCompletenessState.POLICY_REQUIRED: 2,
        SourceCompletenessState.SOURCE_REQUIRED: 3,
        SourceCompletenessState.EXTERNAL_GATE: 4,
        SourceCompletenessState.PARTIAL: 5,
        SourceCompletenessState.UNAVAILABLE: 6,
    }
    exceptions: list[dict[str, object]] = [
        {
            "source": str(item["source"]),
            "state": str(item["state"]),
            "explanation": str(item["explanation"]),
            "owning_domain": _owner(str(item["source"])),
            "mutation_authority": "none",
        }
        for item in sources
        if item["state"] != SourceCompletenessState.AVAILABLE
    ]
    return sorted(
        exceptions,
        key=lambda item: (
            priority.get(SourceCompletenessState(str(item["state"])), 99),
            str(item["source"]),
        ),
    )[:50]


def _entry(
    source: str, state: SourceCompletenessState, count: int, explanation: str
) -> dict[str, object]:
    return {
        "source": source,
        "state": state,
        "evidence_count": count,
        "explanation": explanation,
    }


def _component_state(
    base: SourceCompletenessState, totals: dict[str, Any], key: str
) -> SourceCompletenessState:
    return base if totals.get(key) is not None else SourceCompletenessState.UNAVAILABLE


def _other_cost_state(
    base: SourceCompletenessState, jobs: list[dict[str, Any]]
) -> SourceCompletenessState:
    if not jobs:
        return SourceCompletenessState.UNAVAILABLE
    return (
        base
        if all(item.get("other_direct_cost_minor") is not None for item in jobs)
        else SourceCompletenessState.PARTIAL
    )


def _allocation_state(
    base: SourceCompletenessState, workspace: dict[str, object]
) -> SourceCompletenessState:
    if base in {SourceCompletenessState.CONFLICTING, SourceCompletenessState.STALE}:
        return base
    return (
        base
        if workspace.get("fully_allocated_available") is True
        else SourceCompletenessState.POLICY_REQUIRED
    )


def _identity_state(
    base: SourceCompletenessState, workspace: dict[str, object]
) -> SourceCompletenessState:
    if base in {SourceCompletenessState.CONFLICTING, SourceCompletenessState.STALE}:
        return base
    source_count = _count(workspace.get("source_result_count"))
    job_count = _count(workspace.get("job_count"))
    if source_count == 0:
        return SourceCompletenessState.UNAVAILABLE
    return (
        SourceCompletenessState.AVAILABLE
        if source_count == job_count
        else SourceCompletenessState.PARTIAL
    )


def _category_state(
    base: SourceCompletenessState, workspace: dict[str, object]
) -> SourceCompletenessState:
    if base in {SourceCompletenessState.CONFLICTING, SourceCompletenessState.STALE}:
        return base
    jobs = _count(workspace.get("job_count"))
    if not jobs:
        return SourceCompletenessState.UNAVAILABLE
    return (
        SourceCompletenessState.AVAILABLE
        if _count(workspace.get("unclassified_job_count")) == 0
        else SourceCompletenessState.PARTIAL
    )


def _rollup_state(
    base: SourceCompletenessState, workspace: dict[str, object], key: str
) -> SourceCompletenessState:
    if base in {SourceCompletenessState.CONFLICTING, SourceCompletenessState.STALE}:
        return base
    if _count(workspace.get("job_count")) == 0:
        return SourceCompletenessState.UNAVAILABLE
    return (
        SourceCompletenessState.AVAILABLE
        if _rows(workspace.get(key))
        else SourceCompletenessState.PARTIAL
    )


def _owner(source: str) -> str:
    if source in {"callback_warranty_relationship"}:
        return "jobs_assets"
    if source in {"service_agreement_economics"}:
        return "service_agreements"
    if source in {"capacity_utilization", "workforce_attribution"}:
        return "scheduling_workforce"
    if source in {"cash_working_capital", "accounting_evidence", "settlement"}:
        return "accounting_payments"
    if source in {"procurement_inventory_provenance", "materials"}:
        return "purchasing_inventory"
    return "business_economics"


def _accounting_state(
    base: SourceCompletenessState, readiness: dict[str, Any]
) -> SourceCompletenessState:
    gaps = _rows(readiness.get("policy_gaps"))
    if any("account" in str(item.get("gap_key", "")).casefold() for item in gaps):
        return SourceCompletenessState.POLICY_REQUIRED
    if base is SourceCompletenessState.CONFLICTING:
        return base
    return (
        SourceCompletenessState.PARTIAL
        if base is SourceCompletenessState.AVAILABLE
        else base
    )


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _rows(value: object) -> list[dict[str, Any]]:
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )
