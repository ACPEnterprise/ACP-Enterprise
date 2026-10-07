import json
from pathlib import Path

from app.equipment_readiness.domain import (
    attention_priority,
    can_view_management_attention,
    equipment_checklist_prompt_required,
    equipment_fit,
    projection_state,
    suggested_equipment_checklist_requirement,
)
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX, LaunchRoleCode
from app.platform.permissions.codes import AssetPermission


def test_employee_setting_controls_prompt_independently_of_position():
    assert equipment_checklist_prompt_required("not_required", has_custody_items=True, already_confirmed=False) is False
    assert equipment_checklist_prompt_required("required_at_clock_in", has_custody_items=True, already_confirmed=False) is True
    assert equipment_checklist_prompt_required("required_at_clock_in", has_custody_items=True, already_confirmed=True) is False
    assert equipment_checklist_prompt_required("required_at_clock_in", has_custody_items=False, already_confirmed=False) is False


def test_position_only_supplies_non_authoritative_setup_hint():
    assert suggested_equipment_checklist_requirement("Technician") == "required_at_clock_in"
    assert suggested_equipment_checklist_requirement("Helper") == "not_required"
    assert suggested_equipment_checklist_requirement("Field Service Manager") == "not_required"
from app.equipment_readiness.schemas import DailyConfirmationRequest


def test_equipment_mismatch_is_a_soft_warning_not_scheduling_ineligibility():
    decision = equipment_fit({"DRAIN_MACHINE"}, set())
    assert decision.state == "AVAILABLE_EQUIPMENT_WARNING"
    assert decision.soft_warning is True
    assert decision.continuation_allowed is True
    assert decision.missing_capabilities == ("DRAIN_MACHINE",)


def test_ready_capability_satisfies_job_requirement():
    decision = equipment_fit({"DRAIN_MACHINE"}, {"DRAIN_MACHINE", "TOILET_AUGER"})
    assert decision.state == "AVAILABLE_AND_EQUIPPED"
    assert decision.missing_capabilities == ()


def test_projection_preserves_unknown_incomplete_and_service_states():
    assert projection_state(set(), has_expected_equipment=False) == "EQUIPMENT_UNKNOWN"
    assert projection_state({"ready", "unknown"}, has_expected_equipment=True) == "EQUIPMENT_UNKNOWN"
    assert projection_state({"ready", "out_of_service"}, has_expected_equipment=True) == "EQUIPMENT_OUT_OF_SERVICE"
    assert projection_state({"ready", "incomplete"}, has_expected_equipment=True) == "EQUIPMENT_SET_INCOMPLETE"
    assert projection_state({"ready"}, has_expected_equipment=True) == "AVAILABLE_AND_EQUIPPED"


def test_upcoming_job_elevates_attention_without_beacon():
    assert attention_priority(upcoming_job_impacted=True, state="unknown") == "critical_before_job"
    assert attention_priority(upcoming_job_impacted=False, state="missing") == "needs_attention"
    assert attention_priority(upcoming_job_impacted=False, state="unknown") == "information"


def test_management_routing_uses_roles_not_employee_names():
    assert can_view_management_attention({"FIELD_MANAGER"})
    assert can_view_management_attention({"FIELD_SERVICE_MANAGER"})
    assert can_view_management_attention({"OWNER"})
    assert not can_view_management_attention({"FIELD_TECHNICIAN"})


def test_field_manager_can_read_attention_without_asset_mutation_authority():
    role = next(
        item for item in LAUNCH_ROLE_MATRIX if item.code is LaunchRoleCode.FIELD_MANAGER
    )
    assert AssetPermission.READ in role.permission_codes
    assert AssetPermission.MANAGE not in role.permission_codes
    assert AssetPermission.CUSTODY not in role.permission_codes


def test_owner_catalog_preserves_controlled_asset_serialization_policy():
    contract = json.loads(
        (
            Path(__file__).parents[3]
            / "docs/operations/allcounty-dispatch-critical-equipment.v1.json"
        ).read_text()
    )
    items = {item["code"]: item for item in contract["items"]}
    assert items["K60_DRAIN_MACHINE"]["item_kind"] == "controlled_asset"
    assert items["K60_DRAIN_MACHINE"]["serialization_required"] is True
    assert items["PISTOL_AUGER"]["item_kind"] == "controlled_asset"
    assert items["PISTOL_AUGER"]["serialization_required"] is False
    assert items["TOILET_AUGER"]["item_kind"] == "non_serialized_item"


def test_incomplete_set_requires_explicit_missing_component_evidence():
    payload = DailyConfirmationRequest.model_validate(
        {
            "employee_id": "00000000-0000-0000-0000-000000000001",
            "work_date": "2026-10-06",
            "confirmed_at": "2026-10-06T11:00:00Z",
            "idempotency_key": "confirm-20261006",
            "items": [
                {
                    "catalog_item_id": "00000000-0000-0000-0000-000000000002",
                    "state": "incomplete_set",
                    "missing_components": ["1-1/2-inch jaw"],
                }
            ],
        }
    )
    assert payload.items[0].missing_components == ["1-1/2-inch jaw"]
