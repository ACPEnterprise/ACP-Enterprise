"""Read-only real-workforce acceptance after PR #299 and PR #311 deploy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def evaluate(
    contract: dict[str, Any],
    roster: dict[str, Any],
    administration: dict[str, dict[str, Any]],
    eligibility: list[dict[str, Any]] | None = None,
    completion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected = {item["key"]: item for item in contract["expected_roster"]}
    actual = {item["roster_key"]: item for item in roster.get("items", [])}
    results: list[dict[str, Any]] = []
    eligible_ids = {
        item["employee_id"]
        for item in eligibility or []
        if item.get("eligible") is True
    }
    for key, policy in expected.items():
        item = actual.get(key)
        failures: list[str] = []
        if item is None:
            failures.append("ROSTER_IDENTITY_MISSING")
            results.append({"roster_key": key, "status": "FAIL", "failures": failures})
            continue
        employee_id = item.get("employee_id")
        if employee_id is None:
            failures.append("OWNER_CERTIFICATION_REQUIRED")
        admin = administration.get(employee_id, {}) if employee_id else {}
        for field, ready in (
            ("credential_state", "ACP_LOGIN_READY"),
            ("membership_state", "MEMBERSHIP_READY"),
            ("branch_state", "MAIN_BRANCH_READY"),
            ("role_state", "ROLE_READY"),
            ("timekeeping_state", "LINKED"),
            ("payroll_linkage_state", "LINKED_INPUTS_NOT_EVALUATED"),
        ):
            if item.get(field) != ready:
                failures.append(f"{field.upper()}:{item.get(field, 'UNAVAILABLE')}")
        if policy["classification"] in {"FIELD_MANAGER", "FIELD_TECH", "HELPER"}:
            if item.get("mobile_state") != "MOBILE_READY":
                failures.append(f"MOBILE:{item.get('mobile_state', 'UNAVAILABLE')}")
            if item.get("technician_capability_state") != "TECHNICIAN_CAPABILITY_READY":
                failures.append("TECHNICIAN_CAPABILITY_NOT_READY")
            if eligibility is not None and employee_id not in eligible_ids:
                failures.append("NOT_IN_APPOINTMENT_ELIGIBILITY")
            roles = set(admin.get("role_codes", []))
            missing_roles = set(policy["required_roles"]) - roles
            failures.extend(f"ROLE_MISSING:{code}" for code in sorted(missing_roles))
            permissions = {entry["code"] for entry in admin.get("permissions", [])}
            missing_mobile = set(contract["mobile_permissions"]) - permissions
            failures.extend(
                f"MOBILE_PERMISSION_MISSING:{code}" for code in sorted(missing_mobile)
            )
            forbidden = sorted(
                code
                for code in permissions
                if any(
                    code.startswith(prefix)
                    for prefix in contract["field_forbidden_permission_prefixes"]
                )
            )
            failures.extend(f"FIELD_PRIVILEGE_LEAK:{code}" for code in forbidden)
        results.append(
            {
                "roster_key": key,
                "employee_id": employee_id,
                "status": "PASS" if not failures else "FAIL",
                "failures": failures,
            }
        )
    unexpected = sorted(set(actual) - set(expected))
    completion_employees = {
        item["display_name"]: item for item in (completion or {}).get("employees", [])
    }
    terminated_results: list[dict[str, Any]] = []
    for policy in contract.get("terminated_historical_roster", []):
        item = completion_employees.get(policy["canonical_display_name"])
        failures = []
        if item is None:
            failures.append("TERMINATED_EMPLOYEE_NOT_FOUND")
        else:
            employee_id = item["employee_id"]
            admin = administration.get(employee_id, {})
            if item.get("employment_status") not in {"inactive", "terminated"}:
                failures.append("EMPLOYMENT_NOT_TERMINATED_OR_INACTIVE")
            if admin.get("access_status") not in {"DISABLED", "NOT_LINKED"}:
                failures.append("OPERATIONAL_ACCESS_NOT_DISABLED")
            if admin.get("membership_status") == "active":
                failures.append("MEMBERSHIP_STILL_ACTIVE")
            if admin.get("mobile_readiness") == "READY":
                failures.append("MOBILE_STILL_READY")
            if admin.get("active_assignment_count", 0) != 0:
                failures.append("DISPATCH_ASSIGNMENTS_REMAIN")
            if (
                item.get("final_paper_check_recording")
                != "AVAILABLE_WITHOUT_REACTIVATION"
            ):
                failures.append("FINAL_CHECK_EVIDENCE_PATH_UNAVAILABLE")
            if item.get("operational_reactivation_required") is not False:
                failures.append("FINAL_CHECK_PATH_REQUIRES_REACTIVATION")
        terminated_results.append(
            {
                "roster_key": policy["key"],
                "employee_id": item.get("employee_id") if item else None,
                "expected_final_paper_checks": policy["final_paper_checks_expected"],
                "status": "PASS" if not failures else "FAIL",
                "failures": failures,
            }
        )
    return {
        "contract": contract["contract"],
        "status": "PASS"
        if not unexpected
        and all(item["status"] == "PASS" for item in results)
        and all(item["status"] == "PASS" for item in terminated_results)
        else "FAIL",
        "expected_roster_count": len(expected),
        "actual_roster_count": len(actual),
        "unexpected_roster_keys": unexpected,
        "employees": results,
        "terminated_historical_employees": terminated_results,
        "payroll_non_identity_categories": contract["payroll_non_identity_categories"],
    }


def _get(base_url: str, path: str, token: str) -> Any:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--appointment-id")
    args = parser.parse_args()
    token = args.token_file.read_text(encoding="utf-8").strip()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    roster = _get(args.base_url, "/api/v1/workforce/real-roster", token)
    completion = _get(
        args.base_url, "/api/v1/payroll/cutover-review/completion-readiness", token
    )
    employee_ids = {
        item["employee_id"]
        for item in (*roster["items"], *completion.get("employees", []))
        if item.get("employee_id")
    }
    administration = {
        employee_id: _get(
            args.base_url,
            f"/api/v1/workforce/administration/employees/{employee_id}",
            token,
        )
        for employee_id in employee_ids
    }
    eligibility = (
        _get(
            args.base_url,
            f"/api/v1/dispatch/appointments/{args.appointment_id}/eligible-technicians",
            token,
        )
        if args.appointment_id
        else None
    )
    result = evaluate(contract, roster, administration, eligibility, completion)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
