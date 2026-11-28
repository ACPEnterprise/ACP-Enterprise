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
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
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


def revenue_cycle_flow(
    base_url: str,
    *,
    token: str,
    company_id: str,
    branch_id: str,
    customer_id: str,
    location_id: str,
) -> dict[str, object]:
    """Exercise native Customer-to-cash authority with disposable evidence."""

    def mutate(
        method: str,
        path: str,
        body: dict[str, object],
        expected: set[int] | None = None,
    ) -> dict[str, object]:
        _, result = request(
            base_url,
            method,
            path,
            token=token,
            company_id=company_id,
            branch_id=branch_id,
            body=body,
            expected=expected or {200, 201},
        )
        if not isinstance(result, dict):
            raise AcceptanceFailure(
                f"revenue-cycle endpoint returned no object: {path}"
            )
        return result

    suffix = uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    effective_at = now - timedelta(minutes=5)
    category = mutate(
        "POST",
        "/api/v1/price-book/categories",
        {"code": f"ACC{suffix}", "name": "Acceptance services"},
    )
    tax = mutate(
        "POST",
        "/api/v1/price-book/tax-classifications",
        {
            "code": f"TAX{suffix}",
            "name": "Synthetic local service tax",
            "taxable": True,
        },
    )
    item = mutate(
        "POST",
        "/api/v1/price-book/service-items",
        {
            "branch_id": branch_id,
            "category_id": str(category["id"]),
            "code": f"SERVICE{suffix}",
            "name": "Synthetic leak diagnostic",
            "customer_description": "Disposable revenue-cycle acceptance service",
        },
    )
    version = mutate(
        "POST",
        f"/api/v1/price-book/service-items/{item['id']}/versions",
        {
            "branch_id": branch_id,
            "tax_classification_id": str(tax["id"]),
            "currency": "USD",
            "unit_price": "125.00",
            "effective_at": effective_at.isoformat(),
            "components": [
                {
                    "component_type": "labor",
                    "code": "LABOR",
                    "label": "Synthetic technician labor",
                    "quantity": "1.00",
                    "unit_cost": "40.00",
                },
                {
                    "component_type": "material",
                    "code": "MATERIAL",
                    "label": "Synthetic diagnostic material",
                    "quantity": "1.00",
                    "unit_cost": "10.00",
                },
            ],
        },
    )
    mutate(
        "POST",
        f"/api/v1/price-book/versions/{version['id']}/activate",
        {
            "expected_version": int(version["version"]),
            "reason": "Disposable acceptance activation",
        },
    )
    snapshot = mutate(
        "POST",
        f"/api/v1/price-book/service-items/{item['id']}/snapshots",
        {
            "branch_id": branch_id,
            "quantity": "2.00",
            "currency": "USD",
            "effective_at": now.isoformat(),
            "idempotency_key": f"acceptance-snapshot-{suffix}",
            "historical": False,
        },
    )
    mutate(
        "POST",
        "/api/v1/estimates/tax-policies",
        {
            "branch_id": branch_id,
            "tax_classification_id": str(tax["id"]),
            "currency": "USD",
            "rate_basis_points": 700,
            "version": 1,
            "effective_at": effective_at.isoformat(),
        },
    )
    proposal = {
        "branch_id": branch_id,
        "customer_id": customer_id,
        "service_location_id": location_id,
        "proposal_title": "Synthetic leak diagnostic options",
        "customer_message": "Disposable acceptance proposal; no communication sent.",
        "terms": "Synthetic residential terms",
        "expires_at": (now + timedelta(days=14)).isoformat(),
        "lines": [
            {
                "snapshot_id": str(snapshot["id"]),
                "title": "Synthetic leak diagnostic",
                "description": "Two units from the governed Price Book snapshot.",
            }
        ],
        "discount_type": "percentage",
        "discount_value": "10.00",
    }
    estimate = mutate("POST", "/api/v1/estimates", proposal)
    estimate = mutate(
        "POST",
        f"/api/v1/estimates/{estimate['id']}/revisions",
        {
            **proposal,
            "expected_version": int(estimate["version"]),
            "proposal_title": "Synthetic leak diagnostic — revised",
        },
    )

    lifecycle_at = now + timedelta(minutes=1)

    def estimate_transition(
        action: str, record: dict[str, object]
    ) -> dict[str, object]:
        nonlocal lifecycle_at
        lifecycle_at += timedelta(seconds=1)
        return mutate(
            "POST",
            f"/api/v1/estimates/{record['id']}/{action}",
            {
                "branch_id": branch_id,
                "expected_version": int(record["version"]),
                "occurred_at": lifecycle_at.isoformat(),
            },
        )

    estimate = estimate_transition("send", estimate)
    estimate = estimate_transition("view", estimate)
    lifecycle_at += timedelta(seconds=1)
    estimate = mutate(
        "POST",
        f"/api/v1/estimates/{estimate['id']}/approve",
        {
            "branch_id": branch_id,
            "expected_version": int(estimate["version"]),
            "occurred_at": lifecycle_at.isoformat(),
            "customer_name": "Synthetic Acceptance Customer",
            "customer_email": "acceptance-customer@example.invalid",
            "customer_comment": "Synthetic approval only.",
            "evidence_reference": f"synthetic-acceptance-{suffix}",
        },
    )
    conversion = mutate(
        "POST",
        f"/api/v1/estimates/{estimate['id']}/convert-to-job",
        {
            "branch_id": branch_id,
            "expected_version": int(estimate["version"]),
            "idempotency_key": f"acceptance-estimate-job-{suffix}",
            "job_type_code": "revenue_cycle_acceptance",
            "customer_reported_problem": "Synthetic sold work",
        },
    )
    job = mutate(
        "POST",
        f"/api/v1/jobs/{conversion['job_id']}/activate",
        {"expected_version": 1},
    )
    job = mutate(
        "POST",
        f"/api/v1/jobs/{job['id']}/start",
        {"expected_version": int(job["concurrency_version"])},
    )
    job = mutate(
        "POST",
        f"/api/v1/jobs/{job['id']}/complete",
        {"expected_version": int(job["concurrency_version"])},
    )
    if job.get("status") != "completed":
        raise AcceptanceFailure("sold Job did not reach completed state")
    due_date = (now + timedelta(days=30)).date().isoformat()
    invoice = mutate(
        "POST",
        "/api/v1/invoices",
        {
            "branch_id": branch_id,
            "estimate_id": str(estimate["id"]),
            "job_id": str(job["id"]),
            "due_date": due_date,
            "terms": "Net 30 — synthetic residential terms",
            "idempotency_key": f"acceptance-invoice-{suffix}",
        },
    )
    invoice = mutate(
        "POST",
        f"/api/v1/invoices/{invoice['id']}/issue",
        {
            "branch_id": branch_id,
            "expected_version": int(invoice["version"]),
            "idempotency_key": f"acceptance-issue-{suffix}",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    total = Decimal(str(invoice["total_amount"]))
    first_amount = Decimal("40.00")
    first_payment = mutate(
        "POST",
        f"/api/v1/invoices/{invoice['id']}/manual-payments",
        {
            "branch_id": branch_id,
            "expected_version": int(invoice["version"]),
            "idempotency_key": f"acceptance-cash-{suffix}",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "amount": str(first_amount),
            "payment_method": "cash",
            "reference": f"CASH DRAWER {suffix[-4:]}",
        },
    )
    invoice = first_payment["invoice"]
    if not isinstance(invoice, dict) or invoice.get("status") != "partially_paid":
        raise AcceptanceFailure("partial cash evidence did not preserve Invoice state")
    second_payment = mutate(
        "POST",
        f"/api/v1/invoices/{invoice['id']}/manual-payments",
        {
            "branch_id": branch_id,
            "expected_version": int(invoice["version"]),
            "idempotency_key": f"acceptance-check-{suffix}",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "amount": str(total - first_amount),
            "payment_method": "check",
            "reference": f"CHECK {suffix[-4:]}",
        },
    )
    invoice = second_payment["invoice"]
    if (
        not isinstance(invoice, dict)
        or invoice.get("status") != "paid"
        or Decimal(str(invoice.get("open_amount"))) != 0
    ):
        raise AcceptanceFailure("multiple payments did not close the Invoice exactly")
    _, payment_history = request(
        base_url,
        "GET",
        f"/api/v1/invoices/{invoice['id']}/manual-payments",
        token=token,
        company_id=company_id,
        branch_id=branch_id,
        expected={200},
    )
    if not isinstance(payment_history, list) or len(payment_history) != 2:
        raise AcceptanceFailure("manual payment history did not preserve two receipts")
    if any(
        not isinstance(payment, dict)
        or payment.get("settlement_state") != "not_asserted"
        or payment.get("accounting_state") != "not_posted"
        for payment in payment_history
    ):
        raise AcceptanceFailure(
            "manual payment evidence overstated settlement or posting"
        )
    _, balance = request(
        base_url,
        "GET",
        f"/api/v1/invoices/customers/{customer_id}/balance?as_of={now.date().isoformat()}",
        token=token,
        company_id=company_id,
        branch_id=branch_id,
        expected={200},
    )
    if not isinstance(balance, dict) or Decimal(str(balance.get("open_balance"))) != 0:
        raise AcceptanceFailure("Customer receivable balance did not reconcile to zero")
    cross_tenant_status, _ = request(
        base_url,
        "GET",
        f"/api/v1/invoices/{invoice['id']}",
        token=token,
        company_id=str(uuid4()),
        branch_id=branch_id,
        expected={401, 403},
    )
    if cross_tenant_status not in {401, 403}:
        raise AcceptanceFailure("cross-tenant Invoice access was not denied")
    current_revision = estimate.get("current_revision")
    if (
        not isinstance(current_revision, dict)
        or int(current_revision.get("revision_number", 0)) != 2
    ):
        raise AcceptanceFailure(
            "Estimate revision history did not preserve its successor"
        )
    if Decimal(str(current_revision.get("total_amount"))) != total:
        raise AcceptanceFailure("Estimate and Invoice totals did not reconcile")
    return {
        "price_book_item_id": item["id"],
        "snapshot_id": snapshot["id"],
        "estimate_id": estimate["id"],
        "estimate_number": estimate["estimate_number"],
        "estimate_revision": 2,
        "job_id": job["id"],
        "invoice_id": invoice["id"],
        "invoice_number": invoice["invoice_number"],
        "total": str(total),
        "open_balance": "0.00",
        "payment_count": 2,
        "payment_methods": ["cash", "check"],
        "settlement_state": "not_asserted",
        "accounting_state": "not_posted",
    }


def initial_flow(
    base_url: str,
    credentials: dict[str, object],
    receipt_path: Path,
    smoke_token_path: Path | None,
    revenue_cycle: bool = False,
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
            "window_end_at": window_end.isoformat(),
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
            "customer_reported_problem": "Synthetic acceptance fixture",
        },
        expected={201},
    )
    job_id = str(job["id"])
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
    }
    if revenue_cycle:
        receipt["revenue_cycle"] = revenue_cycle_flow(
            base_url,
            token=owner_token,
            company_id=company_id,
            branch_id=branch_id,
            customer_id=customer_id,
            location_id=location_id,
        )
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
    revenue = receipt.get("revenue_cycle")
    if isinstance(revenue, dict):
        for path in (
            f"/api/v1/estimates/{revenue['estimate_id']}",
            f"/api/v1/jobs/{revenue['job_id']}",
            f"/api/v1/invoices/{revenue['invoice_id']}",
            f"/api/v1/invoices/{revenue['invoice_id']}/manual-payments",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--smoke-token-file", type=Path)
    parser.add_argument("--readback", action="store_true")
    parser.add_argument("--revenue-cycle", action="store_true")
    args = parser.parse_args()
    try:
        credentials = read_json(args.credential_file)
        if args.readback:
            readback(args.base_url, credentials, args.receipt)
        else:
            initial_flow(
                args.base_url,
                credentials,
                args.receipt,
                args.smoke_token_file,
                args.revenue_cycle,
            )
    except AcceptanceFailure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
