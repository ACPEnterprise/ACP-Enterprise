"""Deterministic, read-only planning for bounded owner questions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .conversation import ResolvedPeriod, ResponseMode, interpret_conversation


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
    subject_query: str | None = None
    response_mode: ResponseMode = ResponseMode.NORMAL
    resolved_period: ResolvedPeriod | None = None


DOMAIN_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("customers", ("customer", "location", "history")),
    ("jobs", ("job", "work order", "service history", "open work")),
    (
        "scheduling",
        ("schedule", "appointment", "unscheduled", "unassigned", "where is"),
    ),
    ("dispatch", ("dispatch", "assigned", "technician conflict", "who has")),
    ("estimates", ("estimate", "proposal")),
    ("invoicing", ("invoice", "outstanding", "open ar", "revenue")),
    ("payments", ("payment", "settlement", "cash collected", "paid us", "collect")),
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
    (
        "payroll",
        ("payroll", "ytd", "direct deposit", "pay statement", "holding payroll"),
    ),
    (
        "accounting",
        (
            "accounting",
            "financial report",
            "p&l",
            "balance sheet",
            "qbo",
            "quickbooks",
            "control account",
            "may numbers",
            "sales",
            "revenue",
            "collected",
            "owed to us",
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
    ("price-book", ("price book", "pricing review", "what did we charge")),
    ("beacon", ("beacon", "signal", "needs attention", "worried about")),
    (
        "business-economics",
        (
            "profit",
            "margin",
            "economics",
            "labor cost",
            "material cost",
            "what changed",
            "make money",
        ),
    ),
    ("luminary", ("luminary", "recommendation", "finding", "why did")),
    ("migration", ("migration", "cutover", "source evidence", "qbo acquisition")),
    (
        "launch-readiness",
        (
            "launch",
            "real-world usable",
            "production readiness",
            "what remains",
            "what's broken",
            "what still needs me",
        ),
    ),
    ("audit", ("audit history", "business event")),
)

BRIEFING_PHRASES = (
    "how are we doing",
    "what needs my attention",
    "what happened today",
    "owner briefing",
    "how's business",
    "what's going on today",
    "morning briefing",
    "before i leave",
    "since lunch",
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


def plan_question(
    question: str,
    context_domain: str | None = None,
    topic_domains: tuple[str, ...] = (),
) -> QuestionPlan:
    conversation = interpret_conversation(question)
    normalized = conversation.normalized
    subject_query = _employee_subject(question) if context_domain is None else None
    if conversation.corrected_subject and context_domain == "workforce":
        subject_query = conversation.corrected_subject
    if subject_query is not None:
        subject_domains = frozenset(
            domain
            for domain, terms in DOMAIN_TERMS
            if any(term in normalized for term in terms)
        )
        domains = frozenset({"workforce", *subject_domains})
    elif context_domain:
        question_domains = (
            frozenset(
                domain
                for domain, terms in DOMAIN_TERMS
                if any(term in normalized for term in terms)
            )
            if topic_domains
            else frozenset()
        )
        explicit_switch = (
            bool(question_domains - {context_domain, *topic_domains})
            and not conversation.pronouns
        )
        domains = (
            question_domains
            if explicit_switch
            else frozenset({context_domain, *topic_domains, *question_domains})
        )
    else:
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
        subject_query=subject_query,
        response_mode=conversation.response_mode,
        resolved_period=conversation.period,
    )


def _employee_subject(question: str) -> str | None:
    match = re.fullmatch(
        r"\s*(?:uh\s+)?(?:show me|find|actually,?\s*show me)\s+([\w'’-]+(?:\s+[\w'’-]+){0,3})[?.!]?\s*",
        question,
        re.IGNORECASE,
    )
    return " ".join(match.group(1).split()) if match else None


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
