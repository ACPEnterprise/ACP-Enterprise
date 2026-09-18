"""Owner-friendly, evidence-bound rendering for deterministic LIA answers.

This module interprets only the safe summaries emitted by registered adapters.  It
does not retrieve rows, calculate business truth, or create an action.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .contracts import EvidenceReference


class Responsibility(StrEnum):
    OWNER_ACTION = "OWNER_ACTION"
    EMPLOYEE_ACTION = "EMPLOYEE_ACTION"
    ACCOUNTANT_ACTION = "ACCOUNTANT_ACTION"
    ENGINEERING_ACTION = "ENGINEERING_ACTION"
    EXTERNAL_PROVIDER_ACTION = "EXTERNAL_PROVIDER_ACTION"
    SYSTEM_CALCULATION = "SYSTEM_CALCULATION"
    SOURCE_EVIDENCE_REQUIRED = "SOURCE_EVIDENCE_REQUIRED"


@dataclass(frozen=True)
class OwnerAnswer:
    text: str
    next_action: str


def compose_owner_answer(
    question: str, evidence: tuple[EvidenceReference, ...]
) -> OwnerAnswer:
    """Render a useful conclusion without exceeding the supplied evidence."""
    normalized = question.casefold()
    by_domain = {item.domain: item for item in evidence}

    # Context projections already provide a bounded, entity-specific safe summary.
    contextual = next(
        (
            item
            for item in evidence
            if item.entity_id is not None
            and item.domain in {"customers", "jobs", "workforce", "assets"}
        ),
        None,
    )
    if contextual is not None and len(evidence) == 1:
        return OwnerAnswer(
            text=(
                f"{contextual.state or contextual.label}. "
                f"This is the current authorized {contextual.domain.removesuffix('s')} "
                "summary; any missing history remains listed in the evidence details."
            ),
            next_action=f"Open {contextual.label}",
        )

    if len(by_domain) > 2:
        facts = "; ".join(
            f"{item.label}: {item.count or 0} ({_plain_states(_states(item))})"
            for item in evidence
        )
        return OwnerAnswer(
            "Owner briefing from the currently authorized sources — "
            + facts
            + ". Each source retains its own authority; co-occurrence does not prove causality or shared attribution.",
            "Open the first cited authoritative workspace",
        )

    if "beacon" in by_domain:
        item = by_domain["beacon"]
        states = _states(item)
        active = states.get("active", 0)
        snoozed = states.get("snoozed", 0)
        conclusion = (
            "No active Beacon conditions need attention."
            if active == 0
            else f"Beacon has {active} active condition{'s' if active != 1 else ''} that need review."
        )
        return OwnerAnswer(
            f"{conclusion} {snoozed} condition{'s are' if snoozed != 1 else ' is'} snoozed. "
            "Beacon supplies priority and evidence; LIA does not clear or remediate signals.",
            "Open Beacon attention",
        )

    if "business-economics" in by_domain or "luminary" in by_domain:
        measurement = by_domain.get("business-economics")
        briefing = by_domain.get("luminary")
        economics_parts: list[str] = []
        if measurement is not None:
            states = _states(measurement)
            economics_parts.append(
                f"ACP has {measurement.count or 0} admitted profitability result(s): "
                f"{_plain_states(states)}."
            )
        if briefing is not None:
            economics_parts.append(
                f"The latest Luminary briefing contains {briefing.count or 0} finding(s) "
                f"and is {str(briefing.state or 'unclassified').lower()}."
            )
        economics_parts.append(
            "These are measured results and admitted interpretations; LIA does not recalculate profit or invent causality."
        )
        return OwnerAnswer(" ".join(economics_parts), "Open Business Economics")

    if "migration" in by_domain:
        item = by_domain["migration"]
        states = _states(item)
        if not states or item.count == 0:
            conclusion = (
                "ACP has no admitted migration-run evidence in the authorized scope."
            )
        else:
            conclusion = f"ACP has {item.count} migration-run record(s): {_plain_states(states)}."
        return OwnerAnswer(
            conclusion
            + " Acquisition, admission, and operational availability are separate; this evidence alone does not prove historical records are usable in ACP.",
            "Open Cutover Review",
        )

    if "launch-readiness" in by_domain or "data-quality" in by_domain:
        item = by_domain.get("launch-readiness") or by_domain["data-quality"]
        states = _states(item)
        return OwnerAnswer(
            f"Real-world readiness is not inferred from implementation alone. The current bounded readiness evidence is: {_plain_states(states)}. "
            "Only an end-to-end usable capability with accepted real data is treated as closed.",
            "Open Owner Operations",
        )

    if "accounting" in by_domain:
        accounting_items = tuple(
            item for item in evidence if item.domain == "accounting"
        )
        report = next(
            (
                item
                for item in accounting_items
                if item.authority == "ACP_POSTED_LEDGER_AUTHORITY"
            ),
            None,
        )
        if report is not None:
            return OwnerAnswer(
                f"ACP's posted-ledger report shows {report.state}. "
                "These figures retain the report's period, basis, currency, and integrity authority.",
                "Open Financial Reports",
            )
        item = by_domain["accounting"]
        states = _states(item)
        unavailable = not states or item.count == 0
        if unavailable:
            conclusion = "No authoritative Accounting period evidence is available for this request."
        else:
            conclusion = f"ACP has {item.count} Accounting period record(s): {_plain_states(states)}."
        if any(term in normalized for term in ("p&l", "profit and loss", "sales")):
            conclusion += " Period readiness is not itself a financial statement, so LIA will not manufacture the requested figures."
        return OwnerAnswer(
            conclusion
            + " Source evidence, reconciled Accounting evidence, and ACP-posted ledger authority remain distinct.",
            "Open Financial Reports",
        )

    if "scheduling" in by_domain or "dispatch" in by_domain:
        schedule_parts: list[str] = []
        for domain in ("scheduling", "dispatch"):
            schedule_item = by_domain.get(domain)
            if schedule_item is not None:
                schedule_parts.append(
                    f"{schedule_item.label}: {schedule_item.count or 0} ({_plain_states(_states(schedule_item))})."
                )
        schedule_parts.append(
            "This is current read-only operational evidence; LIA did not schedule, assign, or dispatch work."
        )
        return OwnerAnswer(" ".join(schedule_parts), "Open Scheduling")

    if "payroll" in by_domain:
        item = by_domain["payroll"]
        return OwnerAnswer(
            f"Current Payroll readiness evidence is {_plain_states(_states(item))}. "
            "Protected compensation, tax, withholding, and banking values are excluded. "
            "Readiness metadata does not calculate or execute Payroll.",
            "Open Payroll",
        )

    if "workforce" in by_domain:
        item = by_domain["workforce"]
        return OwnerAnswer(
            f"The authorized Workforce directory contains {item.count or 0} bounded Employee readiness record(s): {_plain_states(_states(item))}. "
            "Role labels do not grant authority, and protected compensation, tax, and banking values are not included.",
            "Open Workforce",
        )

    # For remaining registered domains, retain an honest domain-specific summary.
    facts = "; ".join(
        f"{item.label}: {item.count or 0} ({_plain_states(_states(item))})"
        for item in evidence
    )
    return OwnerAnswer(
        f"Current authorized evidence — {facts}. Missing or unavailable evidence is not treated as zero or false.",
        f"Open {evidence[0].label}",
    )


def _states(item: EvidenceReference) -> dict[str, int]:
    states: dict[str, int] = {}
    for token in (item.state or "").split(","):
        key, separator, raw_count = token.strip().rpartition("=")
        if not separator:
            continue
        try:
            states[key.strip()] = int(raw_count.strip())
        except ValueError:
            continue
    return states


def _plain_states(states: dict[str, int]) -> str:
    if not states:
        return "no accepted records"
    return ", ".join(
        f"{key.replace('_', ' ').replace(':', ' — ').lower()} {count}"
        for key, count in states.items()
    )
