"""Read-only service-line and Branch Economics rollups over admitted Job facts."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Final

CONTRACT_VERSION: Final = "economics.operational-rollups.v1"


def build_operational_rollups(jobs: list[dict[str, Any]]) -> dict[str, object]:
    service_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    branch_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    uncategorized = 0
    for job in jobs:
        category = job.get("service_category")
        if category:
            service_groups[str(category)].append(job)
        else:
            uncategorized += 1
        branch_groups[(str(job["branch_id"]), str(job["branch_name"]))].append(job)

    service_lines = [
        _rollup("SERVICE_LINE", category, category, rows)
        for category, rows in sorted(service_groups.items())
    ]
    branches = [
        _rollup("BRANCH", branch_id, branch_name, rows)
        for (branch_id, branch_name), rows in sorted(branch_groups.items())
    ]
    payload: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "service_lines": service_lines,
        "branches": branches,
        "uncategorized_job_count": uncategorized,
        "limitations": (
            "Uncategorized Jobs are not assigned to a service line.",
            "Known-value subtotals are not represented as complete totals.",
            "Contribution and margin remain unavailable until every required direct cost is authoritative.",
        ),
    }
    payload["digest"] = _digest(payload)
    return payload


def _rollup(
    subject_kind: str,
    subject_id: str,
    display_name: str,
    jobs: list[dict[str, Any]],
) -> dict[str, object]:
    revenue = _metric(jobs, "invoiced_revenue_minor", "currency")
    worked = _metric(jobs, "accepted_worked_seconds", None)
    material = _metric(jobs, "material_cost_minor", None)
    return {
        "subject_kind": subject_kind,
        "subject_id": subject_id,
        "display_name": display_name,
        "job_count": len(jobs),
        "invoiced_revenue": revenue,
        "accepted_worked_seconds": worked,
        "direct_material_cost": material,
        "direct_wage_cost": _unavailable(len(jobs), "job_wage_cost_authority"),
        "other_direct_cost": _unavailable(
            len(jobs), "job_attributed_direct_expense_authority"
        ),
        "direct_contribution_minor": None,
        "contribution_readiness": "PARTIAL" if revenue["known_count"] else "INSUFFICIENT",
    }


def _metric(
    jobs: list[dict[str, Any]], key: str, currency_key: str | None
) -> dict[str, object]:
    known = [job[key] for job in jobs if job.get(key) is not None]
    currencies = (
        {str(job[currency_key]) for job in jobs if job.get(currency_key)}
        if currency_key
        else set()
    )
    complete = len(known) == len(jobs) and (not currency_key or len(currencies) == 1)
    return {
        "state": "AVAILABLE" if complete else "PARTIAL" if known else "SOURCE_REQUIRED",
        "known_count": len(known),
        "missing_count": len(jobs) - len(known),
        "known_value": sum(int(value) for value in known) if known else None,
        "authoritative_total": (
            sum(int(value) for value in known) if complete else None
        ),
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
    }


def _unavailable(job_count: int, requirement: str) -> dict[str, object]:
    return {
        "state": "SOURCE_REQUIRED",
        "known_count": 0,
        "missing_count": job_count,
        "known_value": None,
        "authoritative_total": None,
        "requirement": requirement,
    }


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
