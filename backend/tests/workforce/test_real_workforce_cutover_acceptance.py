import json
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from scripts.real_workforce_cutover_acceptance import _get, evaluate

CONTRACT = json.loads(
    (
        Path(__file__).parents[2] / "operations/real-workforce-cutover-contract.v1.json"
    ).read_text()
)


def test_live_read_includes_explicit_company_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return BytesIO(b'{"status": "ok"}')

    monkeypatch.setattr(
        "scripts.real_workforce_cutover_acceptance.urlopen", fake_urlopen
    )
    company_id = UUID("a56fc415-563b-459c-913f-2e6183109119")

    assert _get("https://beta.example", "/read", "token", company_id) == {
        "status": "ok"
    }
    assert captured["request"].get_header("X-company-id") == str(company_id)
    assert captured["timeout"] == 30


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
            if policy["classification"] in {"FIELD_MANAGER", "FIELD_TECH", "HELPER"}
            else [],
        }
        for item, policy in zip(items, CONTRACT["expected_roster"], strict=True)
    }
    eligibility = [
        {"employee_id": item["employee_id"], "eligible": True}
        for item, policy in zip(items, CONTRACT["expected_roster"], strict=True)
        if policy["classification"] in {"FIELD_MANAGER", "FIELD_TECH", "HELPER"}
    ]
    terminated = []
    for policy in CONTRACT["terminated_historical_roster"]:
        employee_id = f"employee-{policy['key']}"
        terminated.append(
            {
                "employee_id": employee_id,
                "display_name": policy["canonical_display_name"],
                "employment_status": "terminated",
                "operational_reactivation_required": False,
                "final_paper_check_recording": "AVAILABLE_WITHOUT_REACTIVATION",
            }
        )
        administration[employee_id] = {
            "access_status": "DISABLED",
            "membership_status": "inactive",
            "mobile_readiness": "BLOCKED",
            "active_assignment_count": 0,
        }
    result = evaluate(
        CONTRACT,
        {"items": items},
        administration,
        eligibility,
        {"employees": terminated},
    )
    assert result["status"] == "PASS"
    assert result["actual_roster_count"] == 7


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


def test_acceptance_fails_closed_when_terminated_access_is_not_closed() -> None:
    items = [_ready_item(policy) for policy in CONTRACT["expected_roster"]]
    administration = {
        item["employee_id"]: {
            "role_codes": policy["required_roles"],
            "permissions": [],
        }
        for item, policy in zip(items, CONTRACT["expected_roster"], strict=True)
    }
    terminated = []
    for policy in CONTRACT["terminated_historical_roster"]:
        employee_id = f"employee-{policy['key']}"
        terminated.append(
            {
                "employee_id": employee_id,
                "display_name": policy["canonical_display_name"],
                "employment_status": "terminated",
                "operational_reactivation_required": False,
                "final_paper_check_recording": "AVAILABLE_WITHOUT_REACTIVATION",
            }
        )
        administration[employee_id] = {
            "access_status": "ACTIVE",
            "membership_status": "active",
            "mobile_readiness": "READY",
            "active_assignment_count": 1,
        }
    result = evaluate(
        CONTRACT,
        {"items": items},
        administration,
        completion={"employees": terminated},
    )
    assert result["status"] == "FAIL"
    assert all(
        "OPERATIONAL_ACCESS_NOT_DISABLED" in employee["failures"]
        for employee in result["terminated_historical_employees"]
    )
