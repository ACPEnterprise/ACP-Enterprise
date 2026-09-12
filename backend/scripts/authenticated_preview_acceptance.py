"""Bounded authenticated Preview acceptance using an ephemeral synthetic token."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx

PREVIEW_ORIGIN = "https://preview.allcountyhomeservices.com"
SCHEDULE_ROUTE = "/api/v1/operations/jobs/{job_id}/schedule"
FIXTURE_KEY = "acp-employee-beta-v1"

REQUIRED_PERMISSIONS = {
    "csr": frozenset(
        {
            "COMPANY_CUSTOMER_READ",
            "COMPANY_JOB_READ",
            "COMPANY_JOB_MANAGE",
            "COMPANY_SCHEDULING_READ",
            "COMPANY_SCHEDULING_MANAGE",
            "COMPANY_DISPATCH_READ",
        }
    ),
    "employee": frozenset(
        {
            "COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ",
            "COMPANY_JOB_READ",
            "COMPANY_TIMEKEEPING_OWN_READ",
            "COMPANY_PAYROLL_STATEMENT_OWN_READ",
        }
    ),
    "office": frozenset(
        {
            "COMPANY_WORKFORCE_READ",
            "COMPANY_MEMBERSHIP_READ",
            "COMPANY_PAYROLL_COMPENSATION_READ",
            "COMPANY_PAYROLL_TAX_AUTHORITY_READ",
            "COMPANY_PAYROLL_DEDUCTION_AUTHORITY_READ",
            "COMPANY_TIMEKEEPING_ADMIN_READ",
            "COMPANY_PAYROLL_REPORTING_READ",
        }
    ),
    "qbo": frozenset({"COMPANY_ACCOUNTING_REPORT_READ"}),
}

PROHIBITED_PERMISSIONS = frozenset(
    {
        "COMPANY_ADMINISTER",
        "COMPANY_COMMUNICATIONS_MANAGE",
        "COMPANY_PAYMENT_COLLECT",
        "COMPANY_PAYMENT_APPLY",
        "COMPANY_PAYMENT_REFUND",
        "COMPANY_ACCOUNTING_JOURNAL_PREPARE",
        "COMPANY_ACCOUNTING_JOURNAL_POST",
        "COMPANY_ACCOUNTING_JOURNAL_REVERSE",
        "COMPANY_PAYROLL_CALCULATION_EXECUTE",
        "COMPANY_PAYROLL_PAYMENT_EXECUTION_AUTHORIZE",
        "COMPANY_PAYROLL_REMITTANCE_EXECUTE",
        "COMPANY_TIMEKEEPING_OWN_PUNCH",
    }
)
REQUIRED_FIXTURE_REFERENCES = {
    "csr": frozenset({"customer_id", "job_id", "appointment_id"}),
    "employee": frozenset({"job_id"}),
    "office": frozenset({"employee_id"}),
    "qbo": frozenset(),
}


class AcceptanceBlocked(RuntimeError):
    """A safety or authority precondition prevents acceptance."""


@dataclass(frozen=True)
class Probe:
    name: str
    path: str
    params: dict[str, str] | None = None


def validate_origin(origin: str) -> str:
    parsed = urlparse(origin)
    if origin.rstrip("/") != PREVIEW_ORIGIN or parsed.scheme != "https":
        raise AcceptanceBlocked("Only the fixed ACP Preview origin is permitted.")
    return PREVIEW_ORIGIN


def read_token(path: Path) -> str:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise AcceptanceBlocked("Token file must not be accessible by group or others.")
    token = path.read_text(encoding="utf-8").strip()
    if not token or any(character.isspace() for character in token):
        raise AcceptanceBlocked("Token file must contain exactly one opaque token.")
    return token


def read_attestation(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise AcceptanceBlocked("Fixture attestation must not be group/world accessible.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "fixture_key": FIXTURE_KEY,
        "environment": "preview",
        "synthetic_marker": "SYNTHETIC_BETA_ONLY",
        "real_data_access": False,
    }
    if any(payload.get(key) != value for key, value in required.items()):
        raise AcceptanceBlocked("Fixture attestation does not match the Preview contract.")
    for field in (
        "company_id",
        "branch_id",
        "user_id",
        "session_id",
        "persona",
        "release_sha",
        "protected_authority_sha",
        "frontend_sha256",
        "schema_head",
        "audit_event_id",
        "authorized_by",
    ):
        if not payload.get(field):
            raise AcceptanceBlocked(f"Fixture attestation must bind {field}.")
    mutation_allowlist = payload.get("mutation_allowlist")
    if not isinstance(mutation_allowlist, list):
        raise AcceptanceBlocked("Fixture attestation must bind a mutation allowlist.")
    fixture_ids = payload.get("fixture_references")
    if not isinstance(fixture_ids, dict):
        raise AcceptanceBlocked("Fixture attestation must bind fixture references.")
    persona = str(payload.get("persona", ""))
    if persona not in REQUIRED_FIXTURE_REFERENCES or frozenset(fixture_ids) != (
        REQUIRED_FIXTURE_REFERENCES[persona]
    ):
        raise AcceptanceBlocked("Fixture references do not match the persona contract.")
    try:
        for value in fixture_ids.values():
            UUID(str(value))
    except ValueError as error:
        raise AcceptanceBlocked("Fixture references must be UUIDs.") from error
    try:
        expires_at = datetime.fromisoformat(str(payload["expires_at"]))
    except (KeyError, ValueError) as error:
        raise AcceptanceBlocked("Fixture attestation expiry is invalid.") from error
    current = now or datetime.now(timezone.utc)
    if (
        expires_at.tzinfo is None
        or expires_at <= current
        or expires_at > current + timedelta(hours=4)
    ):
        raise AcceptanceBlocked("Fixture attestation is expired or timezone-naive.")
    return payload


def validate_short_lived_token(token: str, *, now: datetime | None = None) -> datetime:
    try:
        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_segment + padding))
        expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AcceptanceBlocked("Token must expose a valid expiry claim.") from error
    current = now or datetime.now(timezone.utc)
    if expires_at <= current or expires_at > current + timedelta(hours=1):
        raise AcceptanceBlocked("Token must be unexpired and expire within one hour.")
    return expires_at


def validate_identity_and_scope(
    *,
    session: dict[str, Any],
    authorization: dict[str, Any],
    expected_company_id: str,
    expected_branch_id: str,
    persona: str,
) -> None:
    email = str(session.get("user", {}).get("normalized_email", "")).lower()
    if not email.endswith(".invalid") or "@allcounty" in email:
        raise AcceptanceBlocked("Acceptance requires a non-routable synthetic identity.")
    if authorization.get("company_id") != expected_company_id:
        raise AcceptanceBlocked("Authenticated Company scope does not match attestation.")
    if authorization.get("active_branch_id") != expected_branch_id:
        raise AcceptanceBlocked("Authenticated Branch scope does not match attestation.")
    permissions = frozenset(authorization.get("permission_codes", ()))
    missing = REQUIRED_PERMISSIONS[persona] - permissions
    forbidden = PROHIBITED_PERMISSIONS & permissions
    if missing:
        raise AcceptanceBlocked(f"Missing required {persona} permissions: {sorted(missing)}")
    if forbidden:
        raise AcceptanceBlocked(
            f"Acceptance identity has prohibited execution permissions: {sorted(forbidden)}"
        )


def probes(persona: str, *, start_at: str, end_at: str) -> tuple[Probe, ...]:
    common = (
        Probe("session", "/api/v1/auth/session"),
        Probe("authorization", "/api/v1/authorization/context"),
        Probe("identity", "/api/v1/identity/me"),
    )
    selected = {
        "csr": (
            Probe("customers", "/api/v1/customers", {"limit": "25", "offset": "0"}),
            Probe("customer_search", "/api/v1/customers/search", {"page_size": "25"}),
            Probe("jobs", "/api/v1/jobs", {"page_size": "25"}),
            Probe("month_calendar", "/api/v1/scheduling/appointments", {"start_at": start_at, "end_at": end_at}),
            Probe("dispatch", "/api/v1/dispatch/board", {"start_at": start_at, "end_at": end_at}),
        ),
        "employee": (
            Probe("my_day", "/api/v1/employee-operations/me/day"),
            Probe("own_time_state", "/api/v1/timekeeping/me/state"),
            Probe("own_job_clock", "/api/v1/timekeeping/me/job-clock"),
            Probe("own_timecard", "/api/v1/timekeeping/me/timecard"),
            Probe("own_payroll_status", "/api/v1/payroll/me/payroll-status"),
            Probe("own_pay_statements", "/api/v1/payroll/me/pay-statements"),
        ),
        "office": (
            Probe("employee_directory", "/api/v1/workforce/employees"),
            Probe("membership_accounts", "/api/v1/company-admin/memberships"),
            Probe("timecard_review", "/api/v1/timekeeping/admin/timecard-review"),
            Probe("payroll_summary", "/api/v1/payroll/operations/summary"),
            Probe("payroll_registers", "/api/v1/payroll/operations/registers"),
        ),
        "qbo": (
            Probe("qbo_cash", "/api/v1/accounting/source-evidence/qbo", {"basis": "cash"}),
            Probe("qbo_accrual", "/api/v1/accounting/source-evidence/qbo", {"basis": "accrual"}),
        ),
    }
    return common + selected[persona]


def fixture_probes(persona: str, references: dict[str, str]) -> tuple[Probe, ...]:
    selected = {
        "csr": (
            Probe("customer_detail", f'/api/v1/customers/{references["customer_id"]}'),
            Probe("job_detail", f'/api/v1/jobs/{references["job_id"]}'),
            Probe(
                "appointment_detail",
                f'/api/v1/scheduling/appointments/{references["appointment_id"]}',
            ),
        ),
        "employee": (Probe("assigned_job", f'/api/v1/jobs/{references["job_id"]}'),),
        "office": (
            Probe("employee_detail", f'/api/v1/workforce/employees/{references["employee_id"]}'),
            Probe(
                "employee_payroll_setup",
                f'/api/v1/payroll/setup/employees/{references["employee_id"]}',
            ),
        ),
        "qbo": (),
    }
    return selected[persona]


def mutation_registry_has_schedule_route(registry_path: Path) -> bool:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    return any(
        entry.get("method") == "POST" and entry.get("path") == SCHEDULE_ROUTE
        for entry in registry.get("entries", ())
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    origin = validate_origin(args.origin)
    token = read_token(args.token_file)
    expires_at = validate_short_lived_token(token)
    attestation = read_attestation(args.attestation_file)
    if attestation["persona"] != args.persona:
        raise AcceptanceBlocked("Fixture attestation persona does not match invocation.")
    if frozenset(attestation.get("permission_codes", ())) != REQUIRED_PERMISSIONS[args.persona]:
        raise AcceptanceBlocked("Fixture attestation permissions are not the exact persona minimum.")
    company_id = attestation["company_id"]
    branch_id = attestation["branch_id"]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Company-ID": company_id,
        "X-Branch-ID": branch_id,
    }
    results: list[dict[str, str | int]] = []
    with httpx.Client(base_url=origin, headers=headers, timeout=20, follow_redirects=False) as client:
        health_response = client.get("/backend-health", headers={})
        if health_response.status_code != 200 or health_response.json().get("version") != attestation["release_sha"]:
            raise AcceptanceBlocked("Preview release does not match the fixture attestation.")
        frontend_response = client.get("/", headers={})
        frontend_digest = hashlib.sha256(frontend_response.content).hexdigest()
        if frontend_response.status_code != 200 or frontend_digest != attestation["frontend_sha256"]:
            raise AcceptanceBlocked("Preview frontend does not match the fixture attestation.")
        session_response = client.get("/api/v1/auth/session")
        authorization_response = client.get("/api/v1/authorization/context")
        for response in (session_response, authorization_response):
            if response.status_code != 200:
                raise AcceptanceBlocked(f"Authentication preflight returned HTTP {response.status_code}.")
        validate_identity_and_scope(
            session=session_response.json(),
            authorization=authorization_response.json(),
            expected_company_id=company_id,
            expected_branch_id=branch_id,
            persona=args.persona,
        )
        selected_probes = probes(args.persona, start_at=args.start_at, end_at=args.end_at)
        selected_probes += fixture_probes(args.persona, attestation["fixture_references"])
        for probe in selected_probes:
            response = client.get(probe.path, params=probe.params)
            if response.status_code != 200:
                raise AcceptanceBlocked(f"{probe.name} returned HTTP {response.status_code}.")
            response.json()  # Require safe JSON projection without retaining or printing it.
            results.append({"name": probe.name, "status": response.status_code})
    return {
        "classification": "AUTHENTICATED_PREVIEW_READ_ACCEPTED",
        "fixture_key": FIXTURE_KEY,
        "persona": args.persona,
        "token_expires_at": expires_at.isoformat(),
        "company_scope_verified": True,
        "branch_scope_verified": True,
        "probes": results,
        "response_data_emitted": False,
        "mutation_performed": False,
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    command.add_argument("--origin", default=PREVIEW_ORIGIN)
    command.add_argument("--persona", choices=sorted(REQUIRED_PERMISSIONS), required=True)
    command.add_argument("--token-file", type=Path, required=True)
    command.add_argument("--attestation-file", type=Path, required=True)
    command.add_argument("--start-at", default="2026-09-01T00:00:00-04:00")
    command.add_argument("--end-at", default="2026-10-01T00:00:00-04:00")
    return command


def main() -> None:
    os.umask(0o077)
    try:
        print(json.dumps(run(parser().parse_args()), sort_keys=True))
    except (AcceptanceBlocked, FileNotFoundError, httpx.HTTPError, json.JSONDecodeError) as error:
        print(json.dumps({"classification": "BLOCKED", "reason": str(error)}))
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
