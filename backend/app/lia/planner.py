"""Deterministic, read-only planning for bounded owner questions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class QuestionIntent(StrEnum):
    CUSTOMER_HISTORY = "CUSTOMER_HISTORY"
    JOB_STATUS = "JOB_STATUS"
    SCHEDULE_STATUS = "SCHEDULE_STATUS"
    WORKFORCE_READINESS = "WORKFORCE_READINESS"
    PAYROLL_READINESS = "PAYROLL_READINESS"
    ACCOUNTING_READINESS = "ACCOUNTING_READINESS"
    ATTENTION = "ATTENTION"
    ECONOMICS = "ECONOMICS"
    LAUNCH_READINESS = "LAUNCH_READINESS"
    BUSINESS_STATUS = "BUSINESS_STATUS"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class QuestionPlan:
    intent: QuestionIntent
    domains: frozenset[str]
    required_sources: tuple[str, ...]


DOMAIN_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("customers", ("customer", "location", "history")),
    ("jobs", ("job", "work order", "service history", "open work")),
    ("scheduling", ("schedule", "appointment", "unscheduled", "unassigned")),
    ("dispatch", ("dispatch", "assigned", "technician conflict")),
    ("estimates", ("estimate", "proposal")),
    ("invoicing", ("invoice", "outstanding", "open ar", "revenue")),
    ("payments", ("payment", "settlement", "cash collected")),
    ("communications", ("communication", "message delivery", "bounce")),
    ("assets", ("asset", "equipment", "fleet", "warranty")),
    (
        "workforce",
        (
            "employee",
            "workforce",
            "technician",
            "readiness evidence",
            "role",
            "branch authority",
        ),
    ),
    ("timekeeping", ("timekeeping", "time entry", "labor hours", "clock")),
    ("payroll", ("payroll", "ytd", "direct deposit", "pay statement")),
    (
        "accounting",
        (
            "accounting",
            "financial report",
            "p&l",
            "balance sheet",
            "qbo",
            "control account",
        ),
    ),
    (
        "data-quality",
        (
            "data quality",
            "source missing",
            "source-only",
            "unreconciled",
            "completeness",
        ),
    ),
    ("price-book", ("price book", "pricing review")),
    ("beacon", ("beacon", "signal", "needs attention")),
    (
        "business-economics",
        (
            "profit",
            "margin",
            "economics",
            "labor cost",
            "material cost",
            "what changed",
        ),
    ),
    ("luminary", ("luminary", "recommendation", "finding", "why did")),
    ("migration", ("migration", "cutover", "source evidence", "qbo acquisition")),
    (
        "launch-readiness",
        ("launch", "real-world usable", "production readiness", "what remains"),
    ),
    ("audit", ("audit history", "business event")),
)

BRIEFING_PHRASES = (
    "how are we doing",
    "what needs my attention",
    "what happened today",
    "owner briefing",
)

OWNER_BRIEFING_DOMAINS = frozenset(
    {
        "beacon",
        "business-economics",
        "luminary",
        "payroll",
        "migration",
        "data-quality",
    }
)


def plan_question(question: str, context_domain: str | None = None) -> QuestionPlan:
    if context_domain:
        domains = frozenset({context_domain})
    else:
        normalized = question.casefold()
        if any(phrase in normalized for phrase in BRIEFING_PHRASES):
            domains = OWNER_BRIEFING_DOMAINS
        else:
            domains = frozenset(
                domain
                for domain, terms in DOMAIN_TERMS
                if any(term in normalized for term in terms)
            )
    intent = _intent(domains)
    return QuestionPlan(
        intent=intent,
        domains=domains,
        required_sources=tuple(sorted(domains)),
    )


def _intent(domains: frozenset[str]) -> QuestionIntent:
    if not domains:
        return QuestionIntent.UNSUPPORTED
    if len(domains) > 1:
        return QuestionIntent.BUSINESS_STATUS
    domain = next(iter(domains))
    return {
        "customers": QuestionIntent.CUSTOMER_HISTORY,
        "jobs": QuestionIntent.JOB_STATUS,
        "scheduling": QuestionIntent.SCHEDULE_STATUS,
        "dispatch": QuestionIntent.SCHEDULE_STATUS,
        "workforce": QuestionIntent.WORKFORCE_READINESS,
        "timekeeping": QuestionIntent.WORKFORCE_READINESS,
        "payroll": QuestionIntent.PAYROLL_READINESS,
        "accounting": QuestionIntent.ACCOUNTING_READINESS,
        "beacon": QuestionIntent.ATTENTION,
        "business-economics": QuestionIntent.ECONOMICS,
        "luminary": QuestionIntent.ECONOMICS,
        "launch-readiness": QuestionIntent.LAUNCH_READINESS,
    }.get(domain, QuestionIntent.BUSINESS_STATUS)
