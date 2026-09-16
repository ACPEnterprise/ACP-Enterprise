"""Owner-friendly interpretation of authoritative Payroll readiness blockers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .contracts import EvidenceReference


class ActionOwner(StrEnum):
    OWNER_ACTION = "OWNER_ACTION"
    EMPLOYEE_ACTION = "EMPLOYEE_ACTION"
    ACCOUNTANT_ACTION = "ACCOUNTANT_ACTION"
    SYSTEM_CALCULATION = "SYSTEM_CALCULATION"
    SOURCE_EVIDENCE_REQUIRED = "SOURCE_EVIDENCE_REQUIRED"


@dataclass(frozen=True, slots=True)
class BlockerGuidance:
    code: str
    meaning: str
    owner: ActionOwner
    order: int
    dependencies: tuple[str, ...]
    next_action: str
    immediately_actionable: bool


GUIDANCE = {
    item.code: item
    for item in (
        BlockerGuidance(
            code="COMPENSATION_MISSING_CONFIGURATION",
            meaning="Authoritative compensation has not been established for this pay period.",
            owner=ActionOwner.OWNER_ACTION,
            order=10,
            dependencies=(),
            next_action=(
                "Set up and approve compensation basis, hourly rate or salary, effective date, "
                "and overtime applicability in Payroll."
            ),
            immediately_actionable=True,
        ),
        BlockerGuidance(
            code="PAYROLL_POLICY_MISSING_CONFIGURATION",
            meaning="The Company does not have one approved Payroll policy effective for this pay period.",
            owner=ActionOwner.OWNER_ACTION,
            order=20,
            dependencies=(),
            next_action=(
                "Complete and approve the Company Payroll policy. Obtain accountant input for "
                "tax or jurisdiction choices that require professional certification."
            ),
            immediately_actionable=True,
        ),
        BlockerGuidance(
            code="TIME_EVIDENCE_MISSING",
            meaning="ACP has no accepted authoritative worked-time evidence for this pay period.",
            owner=ActionOwner.SOURCE_EVIDENCE_REQUIRED,
            order=30,
            dependencies=(),
            next_action=(
                "Enter or import the actual time evidence, resolve timecard exceptions, and approve "
                "the pay-period time snapshot."
            ),
            immediately_actionable=True,
        ),
        BlockerGuidance(
            code="GROSS_PAY_NOT_CALCULATED",
            meaning="ACP has not produced a current gross-pay calculation.",
            owner=ActionOwner.SYSTEM_CALCULATION,
            order=50,
            dependencies=(
                "COMPENSATION_MISSING_CONFIGURATION",
                "PAYROLL_POLICY_MISSING_CONFIGURATION",
                "TIME_EVIDENCE_MISSING",
            ),
            next_action="Run gross-pay calculation after compensation, policy, and accepted time are ready.",
            immediately_actionable=False,
        ),
        BlockerGuidance(
            code="WITHHOLDING_NOT_CALCULATED",
            meaning="ACP has not produced a current withholding calculation.",
            owner=ActionOwner.SYSTEM_CALCULATION,
            order=60,
            dependencies=(
                "PAYROLL_POLICY_MISSING_CONFIGURATION",
                "GROSS_PAY_NOT_CALCULATED",
            ),
            next_action=(
                "After gross pay and approved W-4 and work/residence jurisdiction authority are ready, "
                "run withholding calculation."
            ),
            immediately_actionable=False,
        ),
    )
}


def payroll_guidance_answer(
    question: str, evidence: tuple[EvidenceReference, ...]
) -> str | None:
    payroll = next(
        (
            item
            for item in evidence
            if item.domain == "payroll"
            and item.label.startswith("Payroll readiness for ")
        ),
        None,
    )
    if payroll is None:
        return None
    codes = tuple(sorted(set(re.findall(r"blocker:([A-Z0-9_]+)", payroll.state or ""))))
    if not codes:
        return None
    items = tuple(
        sorted(
            (GUIDANCE[code] for code in codes if code in GUIDANCE),
            key=lambda item: item.order,
        )
    )
    if not items:
        return None
    employee = payroll.label.removeprefix("Payroll readiness for ")
    normalized = question.casefold()
    if "which of those" in normalized or "complete myself" in normalized:
        return _owner_steps(employee, items)
    if "accountant" in normalized:
        return _accountant_steps(employee, items)
    if "what happens after" in normalized or "after i finish" in normalized:
        return _after_steps(employee, items)
    if "what should i do" in normalized or "next" in normalized:
        return _ordered_steps(employee, items)
    if (
        "specifically" in normalized
        or "preventing" in normalized
        or "blocked" in normalized
    ):
        return _blocker_explanation(employee, items)
    if "ready for payroll" in normalized or "payroll ready" in normalized:
        return _readiness_answer(employee, items)
    return None


def _readiness_answer(employee: str, items: tuple[BlockerGuidance, ...]) -> str:
    first = next((item for item in items if item.immediately_actionable), items[0])
    return (
        f"No. {employee} is not ready for Payroll and has {len(items)} recognized blockers. "
        f"First: {first.next_action}"
    )


def _blocker_explanation(employee: str, items: tuple[BlockerGuidance, ...]) -> str:
    groups = []
    for owner, label in (
        (ActionOwner.OWNER_ACTION, "Owner actions"),
        (ActionOwner.SOURCE_EVIDENCE_REQUIRED, "Source evidence required"),
        (ActionOwner.ACCOUNTANT_ACTION, "Accountant actions"),
        (ActionOwner.EMPLOYEE_ACTION, "Employee actions"),
        (ActionOwner.SYSTEM_CALCULATION, "ACP calculations after prerequisites"),
    ):
        values = [item.meaning for item in items if item.owner is owner]
        if values:
            groups.append(f"{label}: " + " ".join(f"{value}" for value in values))
    return f"{employee} is blocked for these reasons. " + " ".join(groups)


def _ordered_steps(employee: str, items: tuple[BlockerGuidance, ...]) -> str:
    ordered_actions = [
        item.next_action
        for item in items
        if item.owner is not ActionOwner.SYSTEM_CALCULATION
    ]
    if any(item.code == "WITHHOLDING_NOT_CALCULATED" for item in items):
        ordered_actions.append(
            "Verify that approved W-4 and work/residence jurisdiction authority exists; "
            "obtain or certify it in the protected Payroll workflow if it is missing."
        )
    ordered_actions.extend(
        item.next_action
        for item in items
        if item.owner is ActionOwner.SYSTEM_CALCULATION
    )
    steps = [
        f"{index}. {action}" for index, action in enumerate(ordered_actions, start=1)
    ]
    steps.append(f"{len(steps) + 1}. Re-run Payroll readiness for {employee}.")
    return f"To make {employee} Payroll-ready, follow this order: " + " ".join(steps)


def _owner_steps(employee: str, items: tuple[BlockerGuidance, ...]) -> str:
    values = [
        item.next_action
        for item in items
        if item.immediately_actionable
        and item.owner
        in {ActionOwner.OWNER_ACTION, ActionOwner.SOURCE_EVIDENCE_REQUIRED}
    ]
    return (
        f"You can work on these now for {employee}: "
        + " ".join(f"{index}. {value}" for index, value in enumerate(values, start=1))
        + " ACP calculations remain unavailable until their prerequisites clear."
    )


def _accountant_steps(employee: str, items: tuple[BlockerGuidance, ...]) -> str:
    explicit = [
        item.next_action
        for item in items
        if item.owner is ActionOwner.ACCOUNTANT_ACTION
    ]
    if explicit:
        return f"The accountant must complete for {employee}: " + " ".join(explicit)
    return (
        f"The current blockers do not prove an accountant-only task for {employee}. "
        "An accountant must provide or certify any tax or jurisdiction policy evidence that the "
        "Payroll setup workflow identifies; ACP will not infer those values."
    )


def _after_steps(employee: str, items: tuple[BlockerGuidance, ...]) -> str:
    calculations = [
        item.next_action
        for item in items
        if item.owner is ActionOwner.SYSTEM_CALCULATION
    ]
    return (
        f"After the owner and source-evidence prerequisites are complete for {employee}, ACP can proceed in order: "
        + " ".join(
            f"{index}. {value}" for index, value in enumerate(calculations, start=1)
        )
        + f" {len(calculations) + 1}. Re-run Payroll readiness and review any remaining blocker."
    )
