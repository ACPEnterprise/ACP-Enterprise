#!/usr/bin/env python3
"""Exercise the assembled application through its real HTTP surface.

This gate is intentionally small and disposable.  It uses a credential file
created by the isolated acceptance harness and never accepts credentials on
the command line or prints them.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


class AcceptanceFailure(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise AcceptanceFailure("acceptance credential or receipt custody is unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceFailure("acceptance input is unavailable or invalid") from error
    if not isinstance(value, dict):
        raise AcceptanceFailure("acceptance input must be an object")
    return value


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    company_id: str | None = None,
    branch_id: str | None = None,
    body: dict[str, object] | None = None,
    expected: set[int] | None = None,
) -> tuple[int, dict[str, object] | list[object]]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if company_id:
        headers["X-Company-ID"] = company_id
    if branch_id:
        headers["X-Branch-ID"] = branch_id
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request_obj = urllib.request.Request(
        f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=15) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
    except (OSError, urllib.error.URLError) as error:
        raise AcceptanceFailure(
            f"assembled application endpoint is unavailable: {method} {path}"
        ) from error
    try:
        value = json.loads(raw or b"{}")
    except json.JSONDecodeError as error:
        raise AcceptanceFailure(
            f"endpoint returned non-JSON status {status}"
        ) from error
    if not isinstance(value, (dict, list)):
        raise AcceptanceFailure(
            f"endpoint returned an invalid JSON value status {status}"
        )
    if expected is not None and status not in expected:
        raise AcceptanceFailure(
            f"unexpected status {status} for {method} {path}: {value}"
        )
    return status, value


def login(base_url: str, email: str, password: str) -> dict[str, object]:
    _, result = request(
        base_url,
        "POST",
        "/api/v1/auth/login",
        body={
            "email": email,
            "password": password,
            "device_label": "isolated-acceptance",
        },
        expected={200},
    )
    if not isinstance(result.get("access_token"), str):
        raise AcceptanceFailure("login response did not contain an access token")
    return result


def tenant_headers(
    company: dict[str, object],
) -> tuple[str, str]:
    company_id = str(company["id"])
    branches = company.get("branches")
    if (
        not isinstance(branches, list)
        or not branches
        or not isinstance(branches[0], dict)
    ):
        raise AcceptanceFailure("authenticated company has no discoverable branch")
    branch_id = str(branches[0]["id"])
    return company_id, branch_id


def initial_flow(
    base_url: str,
    credentials: dict[str, object],
    receipt_path: Path,
    smoke_token_path: Path | None,
    technician_credential_path: Path | None,
) -> None:
    email = str(credentials["email"])
    password = str(credentials["password"])
    owner = login(base_url, email, password)
    owner_token = str(owner["access_token"])
    if smoke_token_path is not None:
        smoke_token_path.write_text(owner_token + "\n", encoding="utf-8")
        smoke_token_path.chmod(0o600)
    _, companies = request(
        base_url,
        "GET",
        "/api/v1/authorization/companies",
        token=owner_token,
        expected={200},
    )
    accessible = (
        companies
        if isinstance(companies, list)
        else companies.get("companies", companies)
    )
    if not isinstance(accessible, list) or len(accessible) != 1:
        raise AcceptanceFailure("owner company discovery was not identity-bound")
    company = accessible[0]
    if not isinstance(company, dict):
        raise AcceptanceFailure("company discovery returned an invalid company")
    company_id, branch_id = tenant_headers(company)

    # This route is deliberately checked without headers: it must fail with a
    # contract validation response rather than silently defaulting to a tenant.
    status, _ = request(
        base_url,
        "GET",
        "/api/v1/customers",
        token=owner_token,
        expected={422},
    )
    if status != 422:
        raise AcceptanceFailure(
            "tenant headers were not required by the customer route"
        )

    suffix = uuid4().hex[:10]
    customer_status, customer = request(
        base_url,
        "POST",
        "/api/v1/customers",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={
            "customer_type": "residential",
            "display_name": f"Integration Acceptance {suffix}",
            "preferred_contact_method": "phone",
            "status": "active",
        },
        expected={201},
    )
    if customer_status != 201 or not customer.get("id"):
        raise AcceptanceFailure(
            "customer creation did not return an authoritative identity"
        )
    customer_id = str(customer["id"])

    # Exercise the same real resource after an authorized request. A random
    # company identifier must be denied by identity-bound authorization; a
    # nonexistent route is never evidence of tenant isolation.
    cross_tenant_status, _ = request(
        base_url,
        "GET",
        f"/api/v1/customers/{customer_id}",
        token=owner_token,
        company_id=str(uuid4()),
        branch_id=branch_id,
        expected={401, 403},
    )
    if cross_tenant_status not in {401, 403}:
        raise AcceptanceFailure("cross-tenant customer access was not denied")
    location_status, location = request(
        base_url,
        "POST",
        f"/api/v1/customers/{customer_id}/locations",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={
            "nickname": "Acceptance Home",
            "address": "100 Integration Way",
            "city": "Clearwater",
            "state": "FL",
            "postal_code": "33755",
            "country": "US",
            "is_primary": True,
        },
        expected={201},
    )
    if location_status != 201 or not location.get("id"):
        raise AcceptanceFailure("service location creation failed")
    location_id = str(location["id"])

    # Workforce eligibility deliberately excludes known synthetic fixtures
    # (notably .invalid users). Use a disposable non-routable test domain that
    # still exercises the normal technician identity path.
    tech_email = f"acceptance-tech-{suffix}@example.test"
    tech_password = secrets.token_urlsafe(24)
    technician_display_name = f"Integration Technician {suffix}"
    _, technician = request(
        base_url,
        "POST",
        "/api/v1/workforce/administration/employee-onboarding",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={
            "request_key": f"acceptance-tech-{suffix}",
            "first_name": "Integration",
            "last_name": f"Technician {suffix}",
            "email": tech_email,
            "phone": "7275550100",
            "branch_id": branch_id,
            "access_profile": "FIELD_TECHNICIAN",
            "temporary_password": tech_password,
            "confirm_temporary_password": tech_password,
            "require_password_change": False,
        },
        expected={201},
    )
    employee_id = str(technician["employee_id"])
    now = datetime.now(timezone.utc)
    next_slot_minutes = ((now.minute // 30) + 1) * 30
    window_start = now.replace(minute=0, second=0, microsecond=0) + timedelta(
        minutes=next_slot_minutes
    )
    window_end = window_start + timedelta(minutes=60)
    readiness_end = window_end + timedelta(minutes=30)
    request(
        base_url,
        "PUT",
        f"/api/v1/workforce/administration/employees/{employee_id}/field-readiness",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={
            "branch_id": branch_id,
            "window_start_at": window_start.isoformat(),
            "window_end_at": readiness_end.isoformat(),
            "reason": "Isolated application integration acceptance",
        },
        expected={200},
    )
    request(
        base_url,
        "PUT",
        f"/api/v1/scheduling/branches/{branch_id}/policy",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={
            "timezone": "America/New_York",
            "active": True,
            "booking_horizon_days": 30,
            "minimum_notice_minutes": 0,
            "slot_interval_minutes": 30,
            "default_capacity_units": "1.00",
            "weekly_intervals": [
                {
                    "day_of_week": day,
                    "start_minute": 0,
                    "end_minute": 1440,
                    "capacity_units": "1.00",
                }
                for day in range(7)
            ],
            "reason": "Isolated application integration acceptance",
        },
        expected={200},
    )
    _, appointment = request(
        base_url,
        "POST",
        "/api/v1/scheduling/appointments",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={
            "idempotency_key": str(uuid4()),
            "branch_id": branch_id,
            "customer_id": customer_id,
            "service_location_id": location_id,
            "arrival_window_start_at": window_start.isoformat(),
            "arrival_window_end_at": window_end.isoformat(),
            "expected_duration_minutes": 60,
            "capacity_units": "1.00",
        },
        expected={201},
    )
    appointment_id = str(appointment["id"])
    _, job = request(
        base_url,
        "POST",
        "/api/v1/jobs/from-appointment",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={
            "appointment_id": appointment_id,
            "job_type_code": "integration_acceptance",
            "priority": "normal",
            "customer_reported_problem": "Integration acceptance service request",
        },
        expected={201},
    )
    job_id = str(job["id"])
    _, job = request(
        base_url,
        "POST",
        f"/api/v1/jobs/{job_id}/activate",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={"expected_version": int(job["concurrency_version"])},
        expected={200},
    )
    _, eligible = request(
        base_url,
        "GET",
        f"/api/v1/dispatch/appointments/{appointment_id}/eligible-technicians",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        expected={200},
    )
    if not isinstance(eligible, list):
        raise AcceptanceFailure("technician eligibility returned an invalid response")
    eligible_technician = next(
        (
            item
            for item in eligible
            if isinstance(item, dict) and str(item.get("employee_id")) == employee_id
        ),
        None,
    )
    if not isinstance(eligible_technician, dict):
        raise AcceptanceFailure(f"synthetic technician was not eligible: {eligible}")
    _, assignment = request(
        base_url,
        "POST",
        f"/api/v1/dispatch/appointments/{appointment_id}/assignment",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={
            "employee_id": employee_id,
            "reason": "Isolated application integration acceptance",
            "idempotency_key": f"acceptance-assignment-{suffix}",
        },
        expected={200},
    )
    if str(assignment.get("primary_employee_id")) != employee_id:
        raise AcceptanceFailure(
            "Dispatch assignment did not preserve technician identity"
        )

    rescheduled_start = window_start + timedelta(minutes=30)
    rescheduled_end = window_end + timedelta(minutes=30)
    _, appointment = request(
        base_url,
        "POST",
        f"/api/v1/scheduling/appointments/{appointment_id}/reschedule",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        body={
            "expected_version": int(appointment["concurrency_version"]),
            "arrival_window_start_at": rescheduled_start.isoformat(),
            "arrival_window_end_at": rescheduled_end.isoformat(),
            "expected_duration_minutes": 60,
            "capacity_units": "1.00",
            "reason_code": "operational_adjustment",
        },
        expected={200},
    )
    if int(appointment.get("reschedule_count", 0)) != 1:
        raise AcceptanceFailure("appointment reschedule was not durably recorded")

    _, assignment = request(
        base_url,
        "GET",
        f"/api/v1/dispatch/appointments/{appointment_id}/assignment",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        expected={200},
    )
    if str(assignment.get("primary_employee_id")) != employee_id:
        raise AcceptanceFailure("reschedule did not preserve the technician assignment")

    _, search = request(
        base_url,
        "GET",
        f"/api/v1/customers/search?query=Integration%20Acceptance%20{suffix}",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        expected={200},
    )
    search_items = search.get("items") if isinstance(search, dict) else None
    if not isinstance(search_items, list) or not any(
        isinstance(item, dict) and str(item.get("id")) == customer_id
        for item in search_items
    ):
        raise AcceptanceFailure("customer search omitted the created customer")

    board_start = rescheduled_start.replace(hour=0, minute=0, second=0, microsecond=0)
    board_end = board_start + timedelta(days=1)
    board_query = urllib.parse.urlencode(
        {
            "start_at": board_start.isoformat(),
            "end_at": board_end.isoformat(),
            "branch_id": branch_id,
        }
    )
    _, board = request(
        base_url,
        "GET",
        f"/api/v1/dispatch/board?{board_query}",
        token=owner_token,
        company_id=company_id,
        branch_id=branch_id,
        expected={200},
    )
    board_items = board.get("items") if isinstance(board, dict) else None
    board_item = next(
        (
            item
            for item in board_items or []
            if isinstance(item, dict)
            and str(item.get("appointment_id")) == appointment_id
        ),
        None,
    )
    if not isinstance(board_item, dict):
        raise AcceptanceFailure("daily dispatch board omitted the appointment")
    board_assignment = board_item.get("assignment")
    if (
        str(board_item.get("status")) not in {"scheduled", "confirmed"}
        or not isinstance(board_assignment, dict)
        or str(board_assignment.get("primary_employee_id")) != employee_id
    ):
        raise AcceptanceFailure("dispatch board status or assignment was incorrect")

    technician_login = login(base_url, tech_email, tech_password)
    tech_token = str(technician_login["access_token"])
    _, day = request(
        base_url,
        "GET",
        "/api/v1/employee-operations/me/day",
        token=tech_token,
        company_id=company_id,
        branch_id=branch_id,
        expected={200},
    )
    if not isinstance(day, dict):
        raise AcceptanceFailure("technician My Day returned an invalid response")
    itinerary = day.get("assignments")
    if not isinstance(itinerary, list) or not any(
        isinstance(item, dict)
        and str(item.get("appointment_id")) == appointment_id
        and str(item.get("job_id")) == job_id
        for item in itinerary
    ):
        raise AcceptanceFailure("technician My Day omitted the assigned work")

    if technician_credential_path is not None:
        if technician_credential_path.exists() or technician_credential_path.is_symlink():
            raise AcceptanceFailure("technician credential output already exists")
        technician_credential_path.write_text(
            json.dumps({"email": tech_email, "password": tech_password}) + "\n",
            encoding="utf-8",
        )
        technician_credential_path.chmod(0o600)

    receipt = {
        "contract": "twelvehats.application-integration-acceptance/v1",
        "company_id": company_id,
        "branch_id": branch_id,
        "customer_id": customer_id,
        "location_id": location_id,
        "job_id": job_id,
        "appointment_id": appointment_id,
        "employee_id": employee_id,
        "technician_email": tech_email,
        "technician_display_name": technician_display_name,
        "customer_display_name": str(customer["display_name"]),
        "appointment_number": str(appointment["appointment_number"]),
        "job_number": str(job["job_number"]),
        "appointment_status": str(board_item["status"]),
        "assignment_version": int(assignment["version"]),
        "reschedule_count": int(appointment["reschedule_count"]),
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    receipt_path.chmod(0o600)
    print(
        json.dumps({"status": "PASS", "phase": "initial", "receipt": receipt_path.name})
    )


def readback(base_url: str, credentials: dict[str, object], receipt_path: Path) -> None:
    receipt = read_json(receipt_path)
    owner = login(base_url, str(credentials["email"]), str(credentials["password"]))
    token = str(owner["access_token"])
    company_id = str(receipt["company_id"])
    branch_id = str(receipt["branch_id"])
    for path in (
        f"/api/v1/customers/{receipt['customer_id']}",
        f"/api/v1/customers/{receipt['customer_id']}/locations",
        f"/api/v1/jobs/{receipt['job_id']}",
        f"/api/v1/scheduling/appointments/{receipt['appointment_id']}",
    ):
        request(
            base_url,
            "GET",
            path,
            token=token,
            company_id=company_id,
            branch_id=branch_id,
            expected={200},
        )
    print(json.dumps({"status": "PASS", "phase": "fresh-session-readback"}))


def technician_readback(
    base_url: str, credentials: dict[str, object], receipt_path: Path
) -> None:
    receipt = read_json(receipt_path)
    technician = login(
        base_url, str(credentials["email"]), str(credentials["password"])
    )
    _, day = request(
        base_url,
        "GET",
        "/api/v1/employee-operations/me/day",
        token=str(technician["access_token"]),
        company_id=str(receipt["company_id"]),
        branch_id=str(receipt["branch_id"]),
        expected={200},
    )
    assignments = day.get("assignments") if isinstance(day, dict) else None
    item = next(
        (
            candidate
            for candidate in assignments or []
            if isinstance(candidate, dict)
            and str(candidate.get("appointment_id")) == receipt["appointment_id"]
            and str(candidate.get("job_id")) == receipt["job_id"]
        ),
        None,
    )
    if not isinstance(item, dict):
        raise AcceptanceFailure("fresh technician session omitted assigned My Day work")
    print(json.dumps({"status": "PASS", "phase": "technician-session-readback"}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--smoke-token-file", type=Path)
    parser.add_argument("--technician-credential-file", type=Path)
    parser.add_argument("--readback", action="store_true")
    parser.add_argument("--technician-readback", action="store_true")
    args = parser.parse_args()
    try:
        credentials = read_json(args.credential_file)
        if args.technician_readback:
            technician_readback(args.base_url, credentials, args.receipt)
        elif args.readback:
            readback(args.base_url, credentials, args.receipt)
        else:
            initial_flow(
                args.base_url,
                credentials,
                args.receipt,
                args.smoke_token_file,
                args.technician_credential_file,
            )
    except AcceptanceFailure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
