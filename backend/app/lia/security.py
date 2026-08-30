from __future__ import annotations

import re

HIGH_IMPACT_PATTERNS = (
    r"\b(approve|issue)\b.*\b(purchase order|po)\b",
    r"\b(pay|refund)\b.*\b(invoice|payment)\b",
    r"\b(post|reverse)\b.*\b(journal|entry)\b",
    r"\b(run|execute|submit)\b.*\bpayroll\b",
    r"\b(reschedule|cancel|dispatch)\b.*\b(job|appointment)\b",
)

EXFILTRATION_PATTERNS = (
    r"\b(client secret|access token|refresh token|private key|system prompt)\b",
    r"\b(bank account|routing number|ssn|social security|tax election)\b",
    r"\b(everyone|all employees|another employee|other branch)\b.*\b(pay|payroll|email|customer|timecard)\b",
)

INJECTION_PATTERNS = (
    r"ignore (all |your |the )?(previous|prior|system|developer) instructions",
    r"reveal (the )?(system|developer) prompt",
    r"change (the )?system prompt",
)

FABRICATION_PATTERNS = (
    r"\b(pretend|assume|make up|fabricate)\b.*\b(paid|profitable|cost|balance|ready|said)\b",
)


def matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    normalized = value.casefold()
    return any(re.search(pattern, normalized) for pattern in patterns)
