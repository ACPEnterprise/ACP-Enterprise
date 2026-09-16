import json
from pathlib import Path

from scripts.real_workforce_cutover_acceptance import evaluate

CONTRACT = json.loads(
    (
        Path(__file__).parents[2] / "operations/real-workforce-cutover-contract.v1.json"
    ).read_text()
)


def _ready_item(policy):
    employee_id = f"employee-{policy['key']}"
    return {
        "roster_key": policy["key"],
        "employee_id": employee_id,
        "credential_state": "ACP_LOGIN_READY",
        "membership_state": "MEMBERSHIP_READY",
        "branch_state": "MAIN_BRANCH_READY",
        "role_state": "ROLE_READY",
        "timekeeping_state": "LINKED",
        "payroll_linkage_state": "LINKED_INPUTS_NOT_EVALUATED",
        "mobile_state": "MOBILE_READY",
        "technician_capability_state": "TECHNICIAN_CAPABILITY_READY",
    }


def test_acceptance_passes_only_for_exact_ready_roster() -> None:
    items = [_ready_item(policy) for policy in CONTRACT["expected_roster"]]
    administration = {
        item["employee_id"]: {
            "role_codes": policy["required_roles"],
            "permissions": [{"code": code} for code in CONTRACT["mobile_permissions"]]
            if policy["classification"] == "FIELD_TECH"
            else [],
        }
        for item, policy in zip(items, CONTRACT["expected_roster"], strict=True)
    }
    eligibility = [
        {"employee_id": item["employee_id"], "eligible": True}
        for item, policy in zip(items, CONTRACT["expected_roster"], strict=True)
        if policy["classification"] == "FIELD_TECH"
    ]
    result = evaluate(CONTRACT, {"items": items}, administration, eligibility)
    assert result["status"] == "PASS"
    assert result["actual_roster_count"] == 8


def test_acceptance_fails_closed_for_unbound_synthetic_and_privilege_leak() -> None:
    items = [_ready_item(policy) for policy in CONTRACT["expected_roster"]]
    items[3]["employee_id"] = None
    items.append({"roster_key": "synthetic-beta", "employee_id": "fixture"})
    administration = {
        item["employee_id"]: {
            "role_codes": ["TECHNICIAN", "ACP_EMPLOYEE_MOBILE"],
            "permissions": [
                *({"code": code} for code in CONTRACT["mobile_permissions"]),
                {"code": "COMPANY_ACCOUNTING_REPORT_READ"},
            ],
        }
        for item in items
        if item.get("employee_id")
    }
    result = evaluate(CONTRACT, {"items": items}, administration)
    assert result["status"] == "FAIL"
    assert result["unexpected_roster_keys"] == ["synthetic-beta"]
    assert "OWNER_CERTIFICATION_REQUIRED" in result["employees"][3]["failures"]
    assert any(
        failure.startswith("FIELD_PRIVILEGE_LEAK:")
        for employee in result["employees"]
        for failure in employee["failures"]
    )
