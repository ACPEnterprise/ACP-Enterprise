"""Prepare and attest sanctioned Preview acceptance identity provisioning."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

CONTRACT_PATH = Path(__file__).parents[1] / "operations/preview-persona-contract-authority.v1.json"


class ProvisioningBlocked(RuntimeError):
    """A provisioning contract precondition is not satisfied."""


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, object]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if (
        contract.get("contract_version") != "om2c.persona.contract.authority.v1"
        or contract.get("environment") != "preview"
        or contract.get("production_access") is not False
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
    selected = persona_contract(load_contract(), persona)
    required = selected.get("fixture_references")
    if not isinstance(required, list) or frozenset(parsed) != frozenset(required):
        raise ProvisioningBlocked("Fixture references do not exactly match the persona contract.")
    return parsed


def persona_contract(contract: dict[str, object], persona: str) -> dict[str, object]:
    personas = contract.get("personas")
    if not isinstance(personas, dict):
        raise ProvisioningBlocked("Unknown acceptance persona.")
    selected = next(
        (
            value
            for value in personas.values()
            if isinstance(value, dict) and value.get("consumer_id") == persona
        ),
        None,
    )
    if not isinstance(selected, dict):
        raise ProvisioningBlocked("Persona contract is invalid.")
    return selected


def permission_digest(permissions: object) -> str:
    if not isinstance(permissions, list) or not all(
        isinstance(value, str) for value in permissions
    ):
        raise ProvisioningBlocked("Persona permissions are invalid.")
    encoded = json.dumps(sorted(permissions), separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def mapping(contract: dict[str, object], key: str) -> dict[str, object]:
    value = contract.get(key)
    if not isinstance(value, dict):
        raise ProvisioningBlocked(f"Canonical {key} contract is invalid.")
    return value


def require_fixed_scope(contract: dict[str, object], company_id: str, branch_id: str) -> None:
    tenant = mapping(contract, "tenant")
    if (
        require_uuid(company_id, "company_id") != tenant.get("company_id")
        or require_uuid(branch_id, "branch_id") != tenant.get("branch_id")
    ):
        raise ProvisioningBlocked("Only the canonical synthetic Company/Branch is allowed.")


def attestation_output_path(path: Path, persona: str) -> Path:
    absolute = path.absolute()
    parts = absolute.parts
    if (
        len(parts) != 8
        or parts[:5] != ("/", "run", "secrets", "acp-preview-acceptance", "v1")
        or not parts[5]
        or parts[6] != persona
        or parts[7] != "attestation.json"
    ):
        raise ProvisioningBlocked("Attestation output path is outside canonical scope.")
    return absolute


def plan(args: argparse.Namespace) -> dict[str, object]:
    contract = load_contract()
    selected = persona_contract(contract, args.persona)
    require_fixed_scope(contract, args.company_id, args.branch_id)
    return {
        "classification": contract["orchestration_state"],
        "mutation_performed": False,
        "environment": "preview",
        "origin": contract["origin"],
        "fixture_key": mapping(contract, "tenant")["fixture_key"],
        "persona": args.persona,
        "persona_code": args.persona.upper() if args.persona != "qbo" else "QBO_READ",
        "synthetic_login": require_synthetic_login(args.synthetic_login),
        "company_id": require_uuid(args.company_id, "company_id"),
        "branch_id": require_uuid(args.branch_id, "branch_id"),
        "permissions": selected["permissions"],
        "prohibited_permissions": contract["prohibited_permissions"],
        "conditional_mutation_endpoints": selected["mutation_allowlist_maximum"],
        "interfaces": contract["provisioning"],
        "audit_actor": contract["audit_actor"],
    }


def attest(args: argparse.Namespace) -> dict[str, object]:
    contract = load_contract()
    selected = persona_contract(contract, args.persona)
    require_fixed_scope(contract, args.company_id, args.branch_id)
    audit_actor = mapping(contract, "audit_actor")
    output = attestation_output_path(args.output, args.persona)
    if output.exists():
        raise ProvisioningBlocked("Refusing to overwrite an existing attestation.")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=args.ttl_seconds)
    try:
        session_expires_at = datetime.fromisoformat(args.session_expires_at)
    except ValueError as error:
        raise ProvisioningBlocked("session_expires_at must be an ISO date-time.") from error
    if (
        session_expires_at.tzinfo is None
        or session_expires_at <= now
        or session_expires_at > now + timedelta(seconds=3600)
    ):
        raise ProvisioningBlocked("Session must be unexpired and expire within one hour.")
    maximum_value = mapping(contract, "lifetimes")["attestation_maximum_seconds"]
    if not isinstance(maximum_value, int):
        raise ProvisioningBlocked("Attestation maximum is invalid.")
    maximum = maximum_value
    if args.ttl_seconds < 1 or args.ttl_seconds > maximum:
        raise ProvisioningBlocked("Attestation lifetime exceeds the contract maximum.")
    requested_mutations = tuple(sorted(set(args.allow_mutation)))
    conditional = selected.get("mutation_allowlist_maximum", [])
    if not isinstance(conditional, list) or any(
        route not in conditional for route in requested_mutations
    ):
        raise ProvisioningBlocked(
            "Mutation allowlist exceeds the selected persona contract."
        )
    if audit_actor.get("primitive_state") != "AVAILABLE":
        raise ProvisioningBlocked("Required Preview fixture service principal is missing.")
    if args.audit_actor_identity != audit_actor.get("identity"):
        raise ProvisioningBlocked("Audit actor identity does not match canonical authority.")
    payload = {
        "fixture_key": mapping(contract, "tenant")["fixture_key"],
        "fixture_version": mapping(contract, "tenant")["fixture_version"],
        "environment": "preview",
        "synthetic_marker": "SYNTHETIC_BETA_ONLY",
        "real_data_access": False,
        "persona": args.persona,
        "company_id": require_uuid(args.company_id, "company_id"),
        "branch_id": require_uuid(args.branch_id, "branch_id"),
        "user_id": require_uuid(args.user_id, "user_id"),
        "session_id": require_uuid(args.session_id, "session_id"),
        "permission_codes": selected["permissions"],
        "permission_digest": permission_digest(selected["permissions"]),
        "mutation_allowlist": requested_mutations,
        "mutation_maximum": conditional,
        "fixture_references": fixture_references(args.fixture_reference, args.persona),
        "deployed_sha": args.deployed_sha,
        "protected_authority_sha": args.protected_authority_sha,
        "frontend_sha256": args.frontend_sha256,
        "schema_head": args.schema_head,
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "session_expires_at": session_expires_at.isoformat(),
        "authorized_by": args.authorized_by,
        "audit_event_id": require_uuid(args.audit_event_id, "audit_event_id"),
        "audit_actor_identity": args.audit_actor_identity,
    }
    for field, value in (
        ("deployed_sha", args.deployed_sha),
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
    release = mapping(contract, "release_contract")
    if (
        args.protected_authority_sha != contract["protected_authority"]
        or args.deployed_sha != release["deployed_sha_required"]
        or args.schema_head != release["schema_head_required"]
        or args.frontend_sha256 != release["frontend_sha256_required"]
    ):
        raise ProvisioningBlocked("Release evidence must match canonical authority.")
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
    seal.add_argument("--audit-actor-identity", required=True)
    seal.add_argument("--deployed-sha", required=True)
    seal.add_argument("--protected-authority-sha", required=True)
    seal.add_argument("--frontend-sha256", required=True)
    seal.add_argument("--schema-head", required=True)
    seal.add_argument("--session-expires-at", required=True)
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
