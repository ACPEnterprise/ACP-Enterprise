from dataclasses import dataclass
from typing import Literal

ReadinessState = Literal[
    "AVAILABLE_AND_EQUIPPED",
    "AVAILABLE_EQUIPMENT_WARNING",
    "EQUIPMENT_UNKNOWN",
    "EQUIPMENT_OUT_OF_SERVICE",
    "EQUIPMENT_SET_INCOMPLETE",
]
EquipmentChecklistRequirement = Literal["not_required", "required_at_clock_in"]


def equipment_checklist_prompt_required(
    requirement: EquipmentChecklistRequirement, *, has_custody_items: bool, already_confirmed: bool
) -> bool:
    """Employee setting is authoritative; custody only supplies checklist items."""
    return requirement == "required_at_clock_in" and has_custody_items and not already_confirmed


@dataclass(frozen=True)
class EquipmentFitDecision:
    state: ReadinessState
    missing_capabilities: tuple[str, ...]
    soft_warning: bool
    continuation_allowed: bool = True


def equipment_fit(
    required_capabilities: set[str], ready_capabilities: set[str]
) -> EquipmentFitDecision:
    missing = tuple(sorted(required_capabilities - ready_capabilities))
    return EquipmentFitDecision(
        state="AVAILABLE_EQUIPMENT_WARNING" if missing else "AVAILABLE_AND_EQUIPPED",
        missing_capabilities=missing,
        soft_warning=bool(missing),
    )


def projection_state(states: set[str], *, has_expected_equipment: bool) -> ReadinessState:
    if not has_expected_equipment or not states or states & {"unknown", "missing"}:
        return "EQUIPMENT_UNKNOWN"
    if "out_of_service" in states:
        return "EQUIPMENT_OUT_OF_SERVICE"
    if "incomplete" in states:
        return "EQUIPMENT_SET_INCOMPLETE"
    return "AVAILABLE_AND_EQUIPPED"


def attention_priority(*, upcoming_job_impacted: bool, state: str) -> str:
    if upcoming_job_impacted:
        return "critical_before_job"
    if state in {"missing", "incomplete", "out_of_service"}:
        return "needs_attention"
    return "information"


def can_view_management_attention(role_codes: set[str]) -> bool:
    return bool(
        role_codes
        & {"OWNER", "COMPANY_ADMINISTRATOR", "FIELD_SERVICE_MANAGER"}
    )
