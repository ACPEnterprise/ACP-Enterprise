"""Owner-question acceptance and refusal metadata.

The matrix never calculates an economic amount. It describes whether existing
authoritative projections can answer a question and where the owner should go
when they cannot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.platform.permissions.codes import (
    AccountingPermission,
    AccountsPayablePermission,
    EconomicsPolicyPermission,
    InvoicePermission,
    PaymentPermission,
)

MATRIX_VERSION: Final = "economics.owner-question-acceptance.v1"


class QuestionDisposition(StrEnum):
    ANSWERABLE = "ANSWERABLE"
    PARTIALLY_ANSWERABLE = "PARTIALLY_ANSWERABLE"
    POLICY_REQUIRED = "POLICY_REQUIRED"
    SOURCE_REQUIRED = "SOURCE_REQUIRED"
    EXTERNAL_GATE = "EXTERNAL_GATE"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class QuestionSpec:
    key: str
    question: str
    answer_source: str
    owning_domains: tuple[str, ...]
    inspect_path: str
    required_permissions: tuple[str, ...] = (
        EconomicsPolicyPermission.MEASUREMENT_READ,
    )
    fixed_disposition: QuestionDisposition | None = None
    limitation: str = ""


_CROSS_DOMAIN_PERMISSIONS = (
    EconomicsPolicyPermission.MEASUREMENT_READ,
    InvoicePermission.READ,
    PaymentPermission.READ,
    AccountsPayablePermission.REPORT_READ,
    AccountingPermission.REPORT_READ,
)


QUESTION_SPECS: Final = (
    QuestionSpec(
        "today",
        "How did we do today?",
        "economics_period",
        ("Business Economics",),
        "/business-economics",
    ),
    QuestionSpec(
        "week",
        "How did we do this week?",
        "economics_period",
        ("Business Economics",),
        "/business-economics",
    ),
    QuestionSpec(
        "month",
        "How did we do this month?",
        "economics_period",
        ("Business Economics",),
        "/business-economics",
    ),
    QuestionSpec(
        "changed",
        "What changed from last period?",
        "period_comparison",
        ("Business Economics",),
        "/business-economics",
    ),
    QuestionSpec(
        "work",
        "How much work did we perform?",
        "earned_work",
        ("Business Economics",),
        "/business-economics",
    ),
    QuestionSpec(
        "collected",
        "How much have we collected?",
        "accounting_cash",
        ("Accounting",),
        "/financial-reports",
        _CROSS_DOMAIN_PERMISSIONS,
        QuestionDisposition.EXTERNAL_GATE,
        "Payment receipts and deposits are not substituted for admitted cash-basis Accounting totals.",
    ),
    QuestionSpec(
        "unpaid",
        "How much completed work remains unpaid?",
        "operational_ar",
        ("Jobs", "Invoices"),
        "/invoices",
        _CROSS_DOMAIN_PERMISSIONS,
    ),
    QuestionSpec(
        "work_cash_difference",
        "Why are performed work and cash different?",
        "three_truth_contract",
        ("Business Economics", "Invoices", "Payments", "Accounting"),
        "/business-economics",
        _CROSS_DOMAIN_PERMISSIONS,
    ),
    QuestionSpec(
        "jobs_most",
        "Which Jobs contributed most?",
        "job_contribution",
        ("Business Economics", "Jobs"),
        "/business-economics",
    ),
    QuestionSpec(
        "jobs_least",
        "Which Jobs contributed least?",
        "job_contribution",
        ("Business Economics", "Jobs"),
        "/business-economics",
    ),
    QuestionSpec(
        "services_most",
        "Which services contributed most?",
        "service_rollup",
        ("Business Economics", "Jobs"),
        "/business-economics",
    ),
    QuestionSpec(
        "services_least",
        "Which services contributed least?",
        "service_rollup",
        ("Business Economics", "Jobs"),
        "/business-economics",
    ),
    QuestionSpec(
        "branch",
        "Which Branch is strongest?",
        "branch_rollup",
        ("Business Economics", "Branches"),
        "/business-economics",
        limitation="Only compatible currency, policy, period, and Branch-scoped evidence may be compared.",
    ),
    QuestionSpec(
        "labor",
        "Where are labor costs moving?",
        "period_comparison",
        ("Business Economics", "Payroll"),
        "/business-economics",
        limitation="Measured movement does not identify an Employee cause.",
    ),
    QuestionSpec(
        "materials",
        "Where are material costs moving?",
        "period_comparison",
        ("Business Economics", "Purchasing", "Inventory"),
        "/business-economics",
        limitation="Measured movement does not establish Vendor causality.",
    ),
    QuestionSpec(
        "vendor",
        "What Vendor obligations are open?",
        "operational_ap",
        ("Accounts Payable",),
        "/accounts-payable",
        _CROSS_DOMAIN_PERMISSIONS,
    ),
    QuestionSpec(
        "profit_cash",
        "Why can profit be positive while cash declines?",
        "three_truth_contract",
        ("Business Economics", "Accounting"),
        "/business-economics",
        _CROSS_DOMAIN_PERMISSIONS,
        QuestionDisposition.EXTERNAL_GATE,
        "A conclusion requires admitted cash-basis Accounting totals; ACP explains the possible timing distinction without asserting a cause.",
    ),
    QuestionSpec(
        "missing",
        "What evidence is missing?",
        "source_readiness",
        ("Business Economics",),
        "/economics-policy",
    ),
    QuestionSpec(
        "decisions",
        "What decisions are waiting on me?",
        "policy_readiness",
        ("Business Economics",),
        "/economics-policy",
    ),
    QuestionSpec(
        "inspect",
        "What should I inspect first?",
        "exception_priority",
        ("Business Economics",),
        "/business-economics",
    ),
    QuestionSpec(
        "stale",
        "What is stale?",
        "source_readiness",
        ("Business Economics",),
        "/business-economics",
    ),
    QuestionSpec(
        "conflicting",
        "What is conflicting?",
        "source_readiness",
        ("Business Economics",),
        "/business-economics",
    ),
    QuestionSpec(
        "unknown",
        "What cannot ACP currently know?",
        "capability_readiness",
        ("Business Economics",),
        "/business-economics",
    ),
)


def owner_question_acceptance_matrix(
    workspace: dict[str, object], permission_codes: frozenset[str]
) -> dict[str, object]:
    quality = str(workspace.get("quality_state") or "unavailable")
    comparison = workspace.get("comparison")
    readiness = workspace.get("readiness")
    rows = []
    for spec in QUESTION_SPECS:
        missing_permissions = sorted(set(spec.required_permissions) - permission_codes)
        disposition = _disposition(
            spec,
            quality=quality,
            comparison=comparison if isinstance(comparison, dict) else {},
            readiness=readiness if isinstance(readiness, dict) else {},
            workspace=workspace,
            missing_permissions=missing_permissions,
        )
        rows.append(
            {
                "key": spec.key,
                "question": spec.question,
                "disposition": disposition.value,
                "answer_source": spec.answer_source,
                "owning_domains": list(spec.owning_domains),
                "inspect_path": spec.inspect_path,
                "missing_permissions": missing_permissions,
                "why": _why(disposition, spec, quality),
                "what_resolves_it": _resolution(disposition, spec, missing_permissions),
                "limitation": spec.limitation or None,
            }
        )
    canonical = {"version": MATRIX_VERSION, "questions": rows}
    return {
        **canonical,
        "matrix_digest": hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "mutation_authority": "none",
    }


def _disposition(
    spec: QuestionSpec,
    *,
    quality: str,
    comparison: dict[str, object],
    readiness: dict[str, object],
    workspace: dict[str, object],
    missing_permissions: list[str],
) -> QuestionDisposition:
    if missing_permissions:
        return QuestionDisposition.NOT_AUTHORIZED
    if spec.fixed_disposition is not None:
        return spec.fixed_disposition
    if spec.key == "changed" and comparison.get("state") != "available":
        return QuestionDisposition.SOURCE_REQUIRED
    if spec.key == "decisions":
        gaps = readiness.get("policy_gaps")
        return (
            QuestionDisposition.POLICY_REQUIRED
            if isinstance(gaps, list) and gaps
            else QuestionDisposition.NOT_APPLICABLE
        )
    if spec.key == "stale":
        return (
            QuestionDisposition.ANSWERABLE
            if quality == "stale"
            else QuestionDisposition.NOT_APPLICABLE
        )
    if spec.key == "conflicting":
        return (
            QuestionDisposition.ANSWERABLE
            if quality == "conflicting"
            else QuestionDisposition.NOT_APPLICABLE
        )
    if spec.key in {"jobs_most", "jobs_least"} and not workspace.get("jobs"):
        return QuestionDisposition.SOURCE_REQUIRED
    if spec.key in {"services_most", "services_least"} and not workspace.get(
        "service_categories"
    ):
        return QuestionDisposition.SOURCE_REQUIRED
    if spec.key == "branch" and not workspace.get("branches"):
        return QuestionDisposition.SOURCE_REQUIRED
    if quality == "complete":
        return QuestionDisposition.ANSWERABLE
    if quality in {"partial", "stale", "conflicting"}:
        return QuestionDisposition.PARTIALLY_ANSWERABLE
    return QuestionDisposition.SOURCE_REQUIRED


def _why(disposition: QuestionDisposition, spec: QuestionSpec, quality: str) -> str:
    return {
        QuestionDisposition.ANSWERABLE: "Accepted evidence can answer this question for the selected scope.",
        QuestionDisposition.PARTIALLY_ANSWERABLE: f"ACP can answer part of this question, but evidence is {quality}.",
        QuestionDisposition.POLICY_REQUIRED: "An explicit owner policy decision is required; ACP applies no default.",
        QuestionDisposition.SOURCE_REQUIRED: "The authoritative source population required for this answer is incomplete or absent.",
        QuestionDisposition.EXTERNAL_GATE: spec.limitation
        or "An external authority must admit this evidence.",
        QuestionDisposition.NOT_AUTHORIZED: "The current session lacks one or more owning-domain read permissions.",
        QuestionDisposition.NOT_APPLICABLE: "No accepted evidence currently matches this condition; this is not the same as zero.",
    }[disposition]


def _resolution(
    disposition: QuestionDisposition, spec: QuestionSpec, missing_permissions: list[str]
) -> str | None:
    if disposition is QuestionDisposition.NOT_AUTHORIZED:
        return "An administrator must grant: " + ", ".join(missing_permissions)
    if disposition is QuestionDisposition.POLICY_REQUIRED:
        return "Review and approve the relevant Economics policy configuration."
    if disposition is QuestionDisposition.SOURCE_REQUIRED:
        return f"Admit complete evidence from: {', '.join(spec.owning_domains)}."
    if disposition is QuestionDisposition.EXTERNAL_GATE:
        return "Wait for the owning domain to admit authoritative evidence; do not substitute operational values."
    return None
