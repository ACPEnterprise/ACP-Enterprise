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
            if item["source"] not in {"settlement"}
        ),
        "limitations": (
            "Source readiness does not select recognition or allocation policy.",
            "Missing evidence is never interpreted as a zero amount.",
            "Settlement and Accounting truth remain owned by their authoritative domains.",
        ),
    }


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
