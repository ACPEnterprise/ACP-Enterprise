"""Deterministic real-world owner-question acceptance corpus.

The corpus records product usefulness, not HTTP availability.  `SAFE_BUT_NOT_USEFUL`
means ACP safely refuses or exposes readiness but cannot yet answer the business
question from admitted evidence.  Cases contain no real customer or employee data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Usefulness(StrEnum):
    USEFUL_PASS = "USEFUL_PASS"
    SAFE_BUT_NOT_USEFUL = "SAFE_BUT_NOT_USEFUL"
    FAIL = "FAIL"


@dataclass(frozen=True)
class OwnerQuestionCase:
    case_id: str
    family: str
    question: str
    expected: Usefulness
    dependency: str | None = None


_QUESTIONS: dict[str, tuple[str, ...]] = {
    "customer": (
        "Show me Sample Customer",
        "What work have we done for them?",
        "What locations do they have?",
        "What is currently open for this Customer?",
        "What did we estimate for this Customer?",
        "What did we invoice this Customer?",
        "What did this Customer pay?",
        "What Customer history is missing?",
    ),
    "job": (
        "Show me Job JOB-000001",
        "What happened on this Job?",
        "Who worked this Job?",
        "Who is assigned to this Job?",
        "When is this Job scheduled?",
        "Was this Job paid?",
        "How much time was recorded for this Job?",
        "What Job evidence is missing?",
    ),
    "employee": (
        "Show me Sample Employee",
        "Is this Employee mobile ready?",
        "Is this Employee payroll ready?",
        "What blocks this Employee?",
        "What can I do for this Employee?",
        "What work history exists for this Employee?",
        "What Employee evidence is missing?",
        "Which Branch authority applies to this Employee?",
    ),
    "scheduling": (
        "What is scheduled today?",
        "What is scheduled tomorrow?",
        "What is scheduled this week?",
        "What needs scheduling?",
        "What is unassigned?",
        "Which appointments are open?",
        "Which appointments are late?",
        "What Scheduling evidence is incomplete?",
    ),
    "dispatch": (
        "What is assigned today?",
        "Which Jobs are unassigned?",
        "What Dispatch conflicts exist?",
        "Who is assigned to this Job?",
        "What Dispatch evidence is incomplete?",
        "Which technicians have assignments?",
        "Why is this Appointment unassigned?",
        "Open Dispatch",
    ),
    "payroll": (
        "Why can't Payroll run?",
        "Who is blocked for Payroll?",
        "What does the owner need to provide for Payroll?",
        "What does the accountant need to provide for Payroll?",
        "Is direct deposit ready?",
        "What Payroll history exists?",
        "What is missing from Payroll YTD?",
        "What will ACP calculate after prerequisites?",
    ),
    "finance": (
        "What QuickBooks data do we have?",
        "Can I see May 2026 financials?",
        "What were sales in May 2026?",
        "Show me the May 2026 P&L",
        "Why is this report source-backed?",
        "What financial evidence remains unreconciled?",
        "What does the accountant need to provide for Accounting?",
        "Which Accounting periods are ready?",
    ),
    "migration": (
        "How much HCP history do we have?",
        "What has not been migrated?",
        "Can I see old Customers?",
        "Are historical estimates imported?",
        "Are historical invoices imported?",
        "What is blocking Customer history?",
        "What source evidence has been acquired?",
        "What acquired evidence is not operationally available?",
    ),
    "luminary": (
        "What does Luminary recommend?",
        "What Luminary findings exist?",
        "Why does this Luminary finding matter?",
        "What evidence supports the Luminary briefing?",
        "What limitations does Luminary report?",
        "What should I inspect after the Luminary briefing?",
        "What changed in the Luminary briefing?",
        "Which Luminary findings are incomplete?",
    ),
    "economics": (
        "What do we know about profitability?",
        "What revenue evidence do we have?",
        "Which Jobs have contribution evidence?",
        "What costs are missing?",
        "Why can't Economics calculate profit?",
        "What would invalidate this Economics result?",
        "Which Economics results are stale?",
        "What Economics evidence should I inspect?",
    ),
    "beacon": (
        "What needs my attention?",
        "What are the active Beacon issues?",
        "Explain this Beacon signal",
        "Why does this Beacon signal matter?",
        "What should I do about this Beacon signal?",
        "What would clear this Beacon signal?",
        "Which Beacon signals are snoozed?",
        "Is this Beacon signal current?",
    ),
    "price_book": (
        "What Price Book review remains?",
        "Which Price Book services are active?",
        "What Price Book evidence is incomplete?",
        "What pricing decisions require the owner?",
        "What pricing decisions require the accountant?",
        "What material mappings are missing from the Price Book?",
        "What labor assumptions are in the Price Book?",
        "Open Price Book review",
    ),
    "mobile": (
        "Which Employees are mobile ready?",
        "Why is this Employee not mobile ready?",
        "What blocks Employee Mobile activation?",
        "Which mobile readiness evidence is missing?",
        "What can the owner do for Mobile readiness?",
        "What requires Apple for Mobile readiness?",
        "Is this Employee login ready?",
        "Open Workforce Mobile readiness",
    ),
    "launch": (
        "What can I actually use today?",
        "What is still broken?",
        "What should I test?",
        "What requires me?",
        "What requires accountant input?",
        "What requires Apple?",
        "What requires engineering?",
        "What prevents Production launch?",
    ),
}


_GATED = {
    # Pending qualified candidates are deliberately not duplicated on this branch.
    ("customer", 0): "CUSTOMER_JOB_RETRIEVAL_CANDIDATE_PENDING_INTEGRATION",
    ("job", 0): "CUSTOMER_JOB_RETRIEVAL_CANDIDATE_PENDING_INTEGRATION",
    **{
        ("payroll", index): "PAYROLL_ACTIONABILITY_CANDIDATE_PENDING_INTEGRATION"
        for index in range(8)
    },
    # Current bounded Accounting adapter exposes readiness, not historical figures.
    **{
        ("finance", index): "FINANCIAL_STATEMENT_AUTHORITY_NOT_ADMITTED"
        for index in (1, 2, 3)
    },
    **{
        ("price_book", index): "PRICE_BOOK_DECISION_PROJECTION_REQUIRED"
        for index in range(3, 7)
    },
    ("mobile", 5): "APPLE_EXTERNAL_GATE",
}


OWNER_QUESTION_CORPUS: tuple[OwnerQuestionCase, ...] = tuple(
    OwnerQuestionCase(
        case_id=f"{family.upper()}-{index + 1:02d}",
        family=family,
        question=question,
        expected=(
            Usefulness.SAFE_BUT_NOT_USEFUL
            if (family, index) in _GATED
            else Usefulness.USEFUL_PASS
        ),
        dependency=_GATED.get((family, index)),
    )
    for family, questions in _QUESTIONS.items()
    for index, question in enumerate(questions)
)


def corpus_totals() -> dict[Usefulness, int]:
    return {
        state: sum(case.expected is state for case in OWNER_QUESTION_CORPUS)
        for state in Usefulness
    }
