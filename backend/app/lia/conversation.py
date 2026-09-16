"""Deterministic conversation interpretation for text and voice LIA.

This module classifies phrasing.  It does not retrieve evidence, retain a
conversation, resolve an identity, or execute an action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum


class ResponseMode(StrEnum):
    BRIEF = "BRIEF"
    NORMAL = "NORMAL"
    DETAILED = "DETAILED"
    EVIDENCE = "EVIDENCE"


class CorrectionKind(StrEnum):
    NONE = "NONE"
    SUBJECT = "SUBJECT"
    PERIOD = "PERIOD"
    BACK = "BACK"
    AMBIGUOUS = "AMBIGUOUS"


class ActionRisk(StrEnum):
    READ = "READ"
    NAVIGATE = "NAVIGATE"
    LOW_IMPACT_OPERATION = "LOW_IMPACT_OPERATION"
    SCHEDULING_CHANGE = "SCHEDULING_CHANGE"
    CUSTOMER_COMMUNICATION = "CUSTOMER_COMMUNICATION"
    PRICE_CHANGE = "PRICE_CHANGE"
    PAYROLL = "PAYROLL"
    ACCOUNTING = "ACCOUNTING"
    MONEY_MOVEMENT = "MONEY_MOVEMENT"
    EMPLOYMENT = "EMPLOYMENT"
    PERMISSION_CHANGE = "PERMISSION_CHANGE"


@dataclass(frozen=True)
class ResolvedPeriod:
    label: str
    starts_on: date
    ends_on: date


@dataclass(frozen=True)
class ActionIntent:
    action_type: str
    risk: ActionRisk
    subject_text: str | None = None
    requested_change: str | None = None


@dataclass(frozen=True)
class ConversationInterpretation:
    normalized: str
    response_mode: ResponseMode
    correction: CorrectionKind
    corrected_subject: str | None
    period: ResolvedPeriod | None
    action: ActionIntent | None
    capability_question: bool
    pronouns: tuple[str, ...]


_ACTION_PATTERNS: tuple[tuple[re.Pattern[str], str, ActionRisk], ...] = (
    (
        re.compile(r"\b(move|reschedule)\b.*\b(job|appointment)\b", re.IGNORECASE),
        "RESCHEDULE_APPOINTMENT",
        ActionRisk.SCHEDULING_CHANGE,
    ),
    (
        re.compile(r"\bassign\b.*\b(job|technician|jason|adam)\b", re.IGNORECASE),
        "ASSIGN_DISPATCH",
        ActionRisk.SCHEDULING_CHANGE,
    ),
    (
        re.compile(
            r"\b(send|email|text)\b.*\b(estimate|invoice|customer|message)\b",
            re.IGNORECASE,
        ),
        "SEND_CUSTOMER_COMMUNICATION",
        ActionRisk.CUSTOMER_COMMUNICATION,
    ),
    (
        re.compile(
            r"\b(raise|lower|change|activate)\b.*\b(price|pricing|percent)\b",
            re.IGNORECASE,
        ),
        "CHANGE_PRICE",
        ActionRisk.PRICE_CHANGE,
    ),
    (
        re.compile(r"\b(approve|run|execute)\b.*\bpayroll\b", re.IGNORECASE),
        "PAYROLL_OPERATION",
        ActionRisk.PAYROLL,
    ),
    (
        re.compile(
            r"\b(post|approve)\b.*\b(journal|accounting|ledger)\b", re.IGNORECASE
        ),
        "ACCOUNTING_OPERATION",
        ActionRisk.ACCOUNTING,
    ),
    (
        re.compile(
            r"^\s*(?:please\s+)?(?:pay|refund|collect|initiate ach)\b", re.IGNORECASE
        ),
        "MONEY_OPERATION",
        ActionRisk.MONEY_MOVEMENT,
    ),
    (
        re.compile(r"\b(hire|fire|terminate|discipline)\b", re.IGNORECASE),
        "EMPLOYMENT_OPERATION",
        ActionRisk.EMPLOYMENT,
    ),
    (
        re.compile(
            r"\b(grant|revoke|change)\b.*\b(permissions?|roles?)\b", re.IGNORECASE
        ),
        "PERMISSION_OPERATION",
        ActionRisk.PERMISSION_CHANGE,
    ),
    (
        re.compile(
            r"\b(order|receive|return)\b.*\b(parts?|materials?)\b", re.IGNORECASE
        ),
        "SUPPLY_OPERATION",
        ActionRisk.LOW_IMPACT_OPERATION,
    ),
)


def interpret_conversation(
    question: str, *, today: date | None = None
) -> ConversationInterpretation:
    normalized = " ".join(question.casefold().replace("’", "'").split())
    anchor = today or datetime.now(UTC).date()
    return ConversationInterpretation(
        normalized=normalized,
        response_mode=_response_mode(normalized),
        correction=_correction(normalized),
        corrected_subject=_corrected_subject(question),
        period=_period(normalized, anchor),
        action=_action(question),
        capability_question=bool(
            re.search(
                r"\bwhat can you do\b|\bwhat can(?:'t| not) you do\b|"
                r"\bcan you (?:schedule|dispatch|change|run|approve|send|pay|post)\b",
                normalized,
            )
        ),
        pronouns=tuple(
            token
            for token in (
                "she",
                "he",
                "they",
                "that customer",
                "that job",
                "that invoice",
                "that appointment",
                "that alert",
                "that recommendation",
                "the first one",
            )
            if re.search(rf"\b{re.escape(token)}\b", normalized)
        ),
    )


def _response_mode(question: str) -> ResponseMode:
    if any(
        phrase in question
        for phrase in ("short version", "just tell me", "what matters")
    ):
        return ResponseMode.BRIEF
    if any(
        phrase in question
        for phrase in ("show me the evidence", "what evidence", "how do you know")
    ):
        return ResponseMode.EVIDENCE
    if any(
        phrase in question
        for phrase in ("more detail", "walk me through", "explain", "why")
    ):
        return ResponseMode.DETAILED
    return ResponseMode.NORMAL


def _correction(question: str) -> CorrectionKind:
    plain = question.rstrip(".!? ")
    if plain in {"go back", "back", "back to that"}:
        return CorrectionKind.BACK
    if plain.startswith("back to "):
        return CorrectionKind.SUBJECT
    if re.search(r"\bactually,? show me\b", question):
        return CorrectionKind.SUBJECT
    if re.search(r"\b(no|actually|wait),? (?:i )?meant\b", question):
        if any(term in question for term in ("month", "may", "june", "week", "period")):
            return CorrectionKind.PERIOD
        return CorrectionKind.SUBJECT
    if any(
        phrase in question
        for phrase in ("the other", "the first one", "the second one")
    ):
        return CorrectionKind.AMBIGUOUS
    return CorrectionKind.NONE


def _corrected_subject(question: str) -> str | None:
    match = re.search(
        r"(?:no|actually|wait)[, ]+(?:i )?meant\s+(.+?)[.!?]?$",
        question,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"actually[, ]+show me\s+(.+?)[.!?]?$", question, re.IGNORECASE
        )
    if not match:
        match = re.search(
            r"back to\s+([\w'’-]+(?:\s+[\w'’-]+){0,3}?)(?:\s*[—–-]|[,.:;!?]|$)",
            question,
            re.IGNORECASE,
        )
    return match.group(1).strip() if match else None


def _period(question: str, today: date) -> ResolvedPeriod | None:
    if "tomorrow" in question:
        day = today + timedelta(days=1)
        return ResolvedPeriod("tomorrow", day, day)
    if "yesterday" in question:
        day = today - timedelta(days=1)
        return ResolvedPeriod("yesterday", day, day)
    if re.search(r"\btoday\b", question):
        return ResolvedPeriod("today", today, today)
    if "last week" in question:
        start = today - timedelta(days=today.weekday() + 7)
        return ResolvedPeriod("last week", start, start + timedelta(days=6))
    if "this week" in question:
        start = today - timedelta(days=today.weekday())
        return ResolvedPeriod("this week", start, start + timedelta(days=6))
    if "last month" in question:
        end = today.replace(day=1) - timedelta(days=1)
        return ResolvedPeriod("last month", end.replace(day=1), end)
    if "this month" in question:
        start = today.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return ResolvedPeriod("this month", start, next_month - timedelta(days=1))
    month_match = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(20\d{2}))?\b",
        question,
    )
    if month_match:
        month = [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ].index(month_match.group(1)) + 1
        year = int(month_match.group(2) or today.year)
        start = date(year, month, 1)
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        return ResolvedPeriod(
            start.strftime("%B %Y"), start, next_month - timedelta(days=1)
        )
    return None


def _action(question: str) -> ActionIntent | None:
    for pattern, action_type, risk in _ACTION_PATTERNS:
        match = pattern.search(question)
        if match:
            return ActionIntent(
                action_type=action_type,
                risk=risk,
                subject_text=question.strip(),
                requested_change=match.group(0),
            )
    return None
