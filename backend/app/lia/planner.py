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
    subject_domain: str | None = None
    subject_query: str | None = None
    response_mode: ResponseMode = ResponseMode.NORMAL
    resolved_period: ResolvedPeriod | None = None


DOMAIN_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("customers", ("customer", "location", "history")),
    ("jobs", ("job", "work order", "service history", "open work")),
    (
        "scheduling",
        (
            "schedule",
            "scheduling",
            "appointment",
            "unscheduled",
            "unassigned",
            "where is",
            "tomorrow look like",
            "busy is",
        ),
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
            "mobile ready",
            "mobile readiness",
            "login ready",
        ),
    ),
    ("timekeeping", ("timekeeping", "time entry", "labor hours", "clock")),
    (
        "payroll",
        (
            "payroll",
            "pay period",
            "ytd",
            "direct deposit",
            "pay statement",
            "holding payroll",
        ),
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
            "source-backed",
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
            "costs are missing",
            "what changed",
            "make money",
            "how did",
        ),
    ),
    ("luminary", ("luminary", "recommendation", "finding", "why did")),
    (
        "migration",
        (
            "migration",
            "migrated",
            "cutover",
            "source evidence",
            "qbo acquisition",
            "acquired evidence",
        ),
    ),
    (
        "launch-readiness",
        (
            "launch",
            "real-world usable",
            "production readiness",
            "what remains",
            "what can i actually use",
            "what is still broken",
            "what should i test",
            "what requires me",
            "what requires accountant input",
            "what requires apple",
            "what requires engineering",
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
    subject = _named_subject(question) if context_domain is None else None
    corrected_context_subject = bool(
        conversation.corrected_subject and context_domain == "workforce"
    )
    if corrected_context_subject:
        subject = ("workforce", conversation.corrected_subject or "")
    subject_domain, subject_query = subject if subject is not None else (None, None)
    if subject_domain == "identity":
        domains = frozenset({"customers", "workforce"})
    elif subject_domain is not None:
        explicit_subject_domains = frozenset(
            domain
            for domain, terms in DOMAIN_TERMS
            if any(term in normalized for term in terms)
        )
        domains = frozenset({subject_domain, *explicit_subject_domains})
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
        related_followups = {
            "customers": {"customers", "jobs", "invoicing", "payments"},
            "jobs": {"jobs", "dispatch", "invoicing", "payments", "scheduling"},
            "workforce": {"workforce", "payroll", "timekeeping", "dispatch"},
        }.get(context_domain, {context_domain})
        explicit_switch = bool(question_domains - related_followups) and not conversation.pronouns
        domains = (
            question_domains
            if explicit_switch
            else frozenset(
                {
                    context_domain,
                    *( () if corrected_context_subject else topic_domains),
                    *question_domains,
                }
                if context_domain == "workforce"
                else {context_domain}
            )
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
        subject_domain=subject_domain,
        subject_query=subject_query,
        response_mode=conversation.response_mode,
        resolved_period=conversation.period,
    )


def _named_subject(question: str) -> tuple[str, str] | None:
    patterns = (
        ("jobs", r"\s*show\s+me\s+job\s+([A-Z0-9-]+)[?.!]?\s*"),
        ("customers", r"\s*show\s+me\s+customer\s+(.+?)[?.!]?\s*"),
        (
            "identity",
            r"\s*(?:uh\s+)?(?:show me|find|actually,?\s*show me)\s+([\w'’&.,-]+(?:\s+[\w'’&.,-]+){0,7})[?.!]?\s*",
        ),
    )
    for domain, pattern in patterns:
        match = re.fullmatch(pattern, question, re.IGNORECASE)
        if match:
            value = " ".join(match.group(1).strip(" .?!").split())
            if domain == "identity" and any(
                term in value.casefold()
                for term in (
                    "schedule",
                    "appointment",
                    "invoice",
                    "estimate",
                    "payroll",
                    "financial",
                    "p&l",
                    "profit",
                    "migration",
                    "beacon",
                )
            ):
                continue
            return (domain, value) if value else None
    return None


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
