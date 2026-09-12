"""Prepare and attest sanctioned Preview acceptance identity provisioning."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

CONTRACT_PATH = (
    Path(__file__).parents[1] / "operations/preview-acceptance-identities.v1.json"
)
REQUIRED_FIXTURE_REFERENCES = {
    "csr": frozenset({"customer_id", "job_id", "appointment_id"}),
    "employee": frozenset({"job_id"}),
    "office": frozenset({"employee_id"}),
    "qbo": frozenset(),
}


class ProvisioningBlocked(RuntimeError):
    """A provisioning contract precondition is not satisfied."""


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, object]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if (
        contract.get("contract_version") != "operator.acceptance.identity.v1"
        or contract.get("environment") != "preview"
        or contract.get("real_data_access") is not False
    ):
        raise ProvisioningBlocked("Unsupported or unsafe acceptance identity contract.")
    return contract


def require_uuid(value: str, field: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as error:
        raise ProvisioningBlocked(f"{field} must be a UUID.") from error


def require_synthetic_login(value: str) -> str:
    login = value.strip().lower()
    if not login.endswith(".invalid") or "@allcounty" in login:
        raise ProvisioningBlocked("Login must be a non-routable synthetic .invalid identity.")
    return login


def fixture_references(values: list[str], persona: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        key, separator, raw_id = value.partition("=")
        if not separator or key in parsed:
            raise ProvisioningBlocked("Fixture references must be unique key=UUID values.")
        parsed[key] = require_uuid(raw_id, key)
    if frozenset(parsed) != REQUIRED_FIXTURE_REFERENCES[persona]:
        raise ProvisioningBlocked("Fixture references do not exactly match the persona contract.")
    return parsed


def persona_contract(contract: dict[str, object], persona: str) -> dict[str, object]:
    personas = contract.get("personas")
    if not isinstance(personas, dict) or persona not in personas:
        raise ProvisioningBlocked("Unknown acceptance persona.")
    selected = personas[persona]
    if not isinstance(selected, dict):
        raise ProvisioningBlocked("Persona contract is invalid.")
    return selected


def plan(args: argparse.Namespace) -> dict[str, object]:
    contract = load_contract()
    selected = persona_contract(contract, args.persona)
    return {
        "classification": "ENTERPRISE_PROVISIONING_PLAN_READY",
        "mutation_performed": False,
        "environment": "preview",
        "origin": contract["origin"],
        "fixture_key": contract["fixture_key"],
        "persona": args.persona,
        "persona_code": selected["persona_code"],
        "synthetic_login": require_synthetic_login(args.synthetic_login),
        "company_id": require_uuid(args.company_id, "company_id"),
        "branch_id": require_uuid(args.branch_id, "branch_id"),
        "permissions": selected["permissions"],
        "prohibited_permissions": contract["prohibited_permissions"],
        "get_endpoints": selected["get_endpoints"],
        "conditional_mutation_endpoints": selected["conditional_mutation_endpoints"],
        "service_sequence": [
            "CompanyAdministrationService.create_role",
            "CompanyAdministrationService.assign_permission",
            "IdentityOnboardingService.initiate",
            "CompanyAdministrationService.add_branch_access",
            "AuthenticationService.authenticate",
            "Enterprise.write_restricted_token_file",
            "acceptance_identity_provisioning_contract.attest",
        ],
        "issuance_boundary": contract["issuance_boundary"],
    }


def attest(args: argparse.Namespace) -> dict[str, object]:
    contract = load_contract()
    selected = persona_contract(contract, args.persona)
    output = args.output.resolve()
    if output.exists():
        raise ProvisioningBlocked("Refusing to overwrite an existing attestation.")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=args.ttl_seconds)
    maximum_value = contract["attestation_maximum_seconds"]
    if not isinstance(maximum_value, int):
        raise ProvisioningBlocked("Attestation maximum is invalid.")
    maximum = maximum_value
    if args.ttl_seconds < 1 or args.ttl_seconds > maximum:
        raise ProvisioningBlocked("Attestation lifetime exceeds the contract maximum.")
    requested_mutations = tuple(sorted(set(args.allow_mutation)))
    conditional = selected.get("conditional_mutation_endpoints", [])
    if not isinstance(conditional, list) or any(
        route not in conditional for route in requested_mutations
    ):
        raise ProvisioningBlocked(
            "Mutation allowlist exceeds the selected persona contract."
        )
    payload = {
        "fixture_key": contract["fixture_key"],
        "environment": "preview",
        "synthetic_marker": contract["synthetic_marker"],
        "real_data_access": False,
        "persona": args.persona,
        "company_id": require_uuid(args.company_id, "company_id"),
        "branch_id": require_uuid(args.branch_id, "branch_id"),
        "user_id": require_uuid(args.user_id, "user_id"),
        "session_id": require_uuid(args.session_id, "session_id"),
        "permission_codes": selected["permissions"],
        "mutation_allowlist": requested_mutations,
        "fixture_references": fixture_references(args.fixture_reference, args.persona),
        "release_sha": args.release_sha,
        "protected_authority_sha": args.protected_authority_sha,
        "frontend_sha256": args.frontend_sha256,
        "schema_head": args.schema_head,
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "authorized_by": args.authorized_by,
        "audit_event_id": require_uuid(args.audit_event_id, "audit_event_id"),
    }
    for field, value in (
        ("release_sha", args.release_sha),
        ("protected_authority_sha", args.protected_authority_sha),
    ):
        if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
            raise ProvisioningBlocked(f"{field} must be a lowercase full Git SHA.")
    if len(args.frontend_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in args.frontend_sha256
    ):
        raise ProvisioningBlocked("frontend_sha256 must be a lowercase SHA-256 digest.")
    if not args.schema_head:
        raise ProvisioningBlocked("schema_head is required.")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.chmod(0o600)
    return {
        "classification": "FIXTURE_ATTESTATION_WRITTEN",
        "path": str(output),
        "persona": args.persona,
        "expires_at": expires_at.isoformat(),
        "credential_material_emitted": False,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(required=True)
    prepare = commands.add_parser("plan")
    prepare.add_argument("--persona", choices=("csr", "employee", "office", "qbo"), required=True)
    prepare.add_argument("--synthetic-login", required=True)
    prepare.add_argument("--company-id", required=True)
    prepare.add_argument("--branch-id", required=True)
    prepare.set_defaults(action=plan)
    seal = commands.add_parser("attest")
    seal.add_argument("--persona", choices=("csr", "employee", "office", "qbo"), required=True)
    seal.add_argument("--company-id", required=True)
    seal.add_argument("--branch-id", required=True)
    seal.add_argument("--user-id", required=True)
    seal.add_argument("--session-id", required=True)
    seal.add_argument("--audit-event-id", required=True)
    seal.add_argument("--authorized-by", required=True)
    seal.add_argument("--release-sha", required=True)
    seal.add_argument("--protected-authority-sha", required=True)
    seal.add_argument("--frontend-sha256", required=True)
    seal.add_argument("--schema-head", required=True)
    seal.add_argument("--allow-mutation", action="append", default=[])
    seal.add_argument("--fixture-reference", action="append", default=[])
    seal.add_argument("--ttl-seconds", type=int, default=3600)
    seal.add_argument("--output", type=Path, required=True)
    seal.set_defaults(action=attest)
    return root


def main() -> None:
    os.umask(0o077)
    try:
        arguments = parser().parse_args()
        print(json.dumps(arguments.action(arguments), sort_keys=True))
    except (FileNotFoundError, json.JSONDecodeError, ProvisioningBlocked) as error:
        print(json.dumps({"classification": "BLOCKED", "reason": str(error)}))
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
