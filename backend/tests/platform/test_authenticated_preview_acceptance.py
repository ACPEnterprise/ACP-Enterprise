from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.acceptance_identity_provisioning_contract import (
    ProvisioningBlocked,
    attest,
    plan,
)
from scripts.authenticated_preview_acceptance import (
    PREVIEW_ORIGIN,
    PROHIBITED_PERMISSIONS,
    REQUIRED_PERMISSIONS,
    SCHEDULE_ROUTE,
    AcceptanceBlocked,
    mutation_registry_has_schedule_route,
    read_attestation,
    read_token,
    validate_identity_and_scope,
    validate_origin,
    validate_short_lived_token,
)

CONTRACT_PATH = Path(__file__).parents[2] / "operations/preview-acceptance-identities.v1.json"
MATRIX_PATH = Path(__file__).parents[2] / "operations/preview-authenticated-acceptance-matrix.v1.json"
REPORT_PATH = Path(__file__).parents[2] / "operations/preview-authenticated-acceptance-report.v1.json"
MUTATION_REGISTRY_PATH = (
    Path(__file__).parents[2] / "app/platform/idempotency/mutation-coverage.v1.json"
)


def _token(expires_at: datetime) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": int(expires_at.timestamp())}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_origin_is_fixed_to_preview() -> None:
    assert validate_origin("https://preview.allcountyhomeservices.com")
    for origin in ("https://allcountyhomeservices.com", "http://preview.allcountyhomeservices.com"):
        with pytest.raises(AcceptanceBlocked):
            validate_origin(origin)


def test_token_file_is_private_and_token_is_short_lived(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    token_file = tmp_path / "token"
    token_file.write_text(_token(now + timedelta(minutes=15)), encoding="utf-8")
    token_file.chmod(0o600)
    token = read_token(token_file)
    assert validate_short_lived_token(token, now=now) == (
        now + timedelta(minutes=15)
    ).replace(microsecond=0)
    token_file.chmod(0o640)
    with pytest.raises(AcceptanceBlocked):
        read_token(token_file)
    with pytest.raises(AcceptanceBlocked):
        validate_short_lived_token(_token(now + timedelta(hours=2)), now=now)


def test_identity_scope_and_permissions_fail_closed() -> None:
    session = {"user": {"normalized_email": "operator@acceptance.invalid"}}
    authorization = {
        "company_id": "company",
        "active_branch_id": "branch",
        "permission_codes": [
            "COMPANY_CUSTOMER_READ",
            "COMPANY_JOB_READ",
            "COMPANY_JOB_MANAGE",
            "COMPANY_SCHEDULING_READ",
            "COMPANY_SCHEDULING_MANAGE",
            "COMPANY_DISPATCH_READ",
        ],
    }
    validate_identity_and_scope(
        session=session,
        authorization=authorization,
        expected_company_id="company",
        expected_branch_id="branch",
        persona="csr",
    )
    authorization["permission_codes"].append("COMPANY_PAYMENT_COLLECT")
    with pytest.raises(AcceptanceBlocked):
        validate_identity_and_scope(
            session=session,
            authorization=authorization,
            expected_company_id="company",
            expected_branch_id="branch",
            persona="csr",
        )


def test_attestation_binds_synthetic_preview_scope(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    attestation = tmp_path / "attestation.json"
    attestation.write_text(
        json.dumps(
            {
                "fixture_key": "acp-employee-beta-v1",
                "environment": "preview",
                "synthetic_marker": "SYNTHETIC_BETA_ONLY",
                "real_data_access": False,
                "company_id": "company",
                "branch_id": "branch",
                "user_id": "user",
                "session_id": "session",
                "persona": "csr",
                "release_sha": "a" * 40,
                "protected_authority_sha": "b" * 40,
                "frontend_sha256": "c" * 64,
                "schema_head": "d4f6h8j0l2n4",
                "permission_codes": sorted(
                    {
                        "COMPANY_CUSTOMER_READ",
                        "COMPANY_JOB_READ",
                        "COMPANY_JOB_MANAGE",
                        "COMPANY_SCHEDULING_READ",
                        "COMPANY_SCHEDULING_MANAGE",
                        "COMPANY_DISPATCH_READ",
                    }
                ),
                "issued_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=2)).isoformat(),
                "authorized_by": "enterprise-release",
                "audit_event_id": "audit",
            }
        ),
        encoding="utf-8",
    )
    attestation.chmod(0o600)
    assert read_attestation(attestation, now=now)["company_id"] == "company"
    payload = json.loads(attestation.read_text(encoding="utf-8"))
    payload["real_data_access"] = True
    attestation.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AcceptanceBlocked):
        read_attestation(attestation, now=now)


def test_schedule_mutation_remains_blocked_until_registry_is_authoritative(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"entries": []}), encoding="utf-8")
    assert not mutation_registry_has_schedule_route(registry)
    registry.write_text(
        json.dumps({"entries": [{"method": "POST", "path": SCHEDULE_ROUTE}]}),
        encoding="utf-8",
    )
    assert mutation_registry_has_schedule_route(registry)


def test_provisioning_contract_matches_runner_personas() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["origin"] == PREVIEW_ORIGIN
    assert contract["environment"] == "preview"
    assert contract["real_data_access"] is False
    assert contract["access_token_maximum_seconds"] == 3600
    assert contract["one_identity_per_persona"] is True
    assert set(contract["personas"]) == set(REQUIRED_PERMISSIONS)
    assert frozenset(contract["prohibited_permissions"]) == PROHIBITED_PERMISSIONS
    for name, persona in contract["personas"].items():
        permissions = frozenset(persona["permissions"])
        assert permissions == REQUIRED_PERMISSIONS[name]
        assert not permissions & PROHIBITED_PERMISSIONS
        assert all(path.startswith("/api/v1/") for path in persona["get_endpoints"])


def test_execution_matrix_and_report_use_exact_result_vocabulary() -> None:
    expected = {
        "PASS",
        "FAIL_PRODUCT_DEFECT",
        "BLOCKED_AUTH",
        "BLOCKED_MUTATION_GOVERNANCE",
        "BLOCKED_SOURCE_DATA",
        "BLOCKED_DEPENDENCY",
        "NOT_APPLICABLE",
    }
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert set(matrix["result_classifications"]) == expected
    assert set(report["allowed_classifications"]) == expected
    assert len(matrix["mutation_governance_routes"]) == 5
    assert {
        route["protected_state"] for route in matrix["mutation_governance_routes"]
    } == {"CLASSIFIED"}
    assert all(
        case["method"] == "GET" or case.get("gate")
        for case in matrix["cases"]
    )
    assert {
        "persona",
        "route_workflow",
        "test_data_identity",
        "expected_result",
        "observed_result",
        "classification",
        "evidence_reference",
        "defect_owner",
        "cleanup_revocation_status",
    } <= set(report["results"][0])


def test_five_tracked_mutations_are_classified_by_current_authority() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    registry = json.loads(MUTATION_REGISTRY_PATH.read_text(encoding="utf-8"))
    classified = {f'{entry["method"]} {entry["path"]}' for entry in registry["entries"]}
    assert {
        route["identity"] for route in matrix["mutation_governance_routes"]
    } <= classified


def test_enterprise_plan_is_non_mutating_and_rejects_real_login() -> None:
    arguments = type(
        "Arguments",
        (),
        {
            "persona": "csr",
            "synthetic_login": "csr@acceptance.invalid",
            "company_id": "00000000-0000-0000-0000-000000000001",
            "branch_id": "00000000-0000-0000-0000-000000000002",
        },
    )()
    assert plan(arguments)["mutation_performed"] is False
    arguments.synthetic_login = "person@example.com"
    with pytest.raises(ProvisioningBlocked):
        plan(arguments)


def test_enterprise_attestation_is_restricted_and_contains_no_token(tmp_path: Path) -> None:
    output = tmp_path / "attestation.json"
    arguments = type(
        "Arguments",
        (),
        {
            "persona": "employee",
            "company_id": "00000000-0000-0000-0000-000000000001",
            "branch_id": "00000000-0000-0000-0000-000000000002",
            "user_id": "00000000-0000-0000-0000-000000000003",
            "session_id": "00000000-0000-0000-0000-000000000004",
            "audit_event_id": "00000000-0000-0000-0000-000000000005",
            "authorized_by": "enterprise-release",
            "release_sha": "a" * 40,
            "protected_authority_sha": "b" * 40,
            "frontend_sha256": "c" * 64,
            "schema_head": "d4f6h8j0l2n4",
            "ttl_seconds": 3600,
            "output": output,
        },
    )()
    result = attest(arguments)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result["credential_material_emitted"] is False
    assert output.stat().st_mode & 0o077 == 0
    assert "token" not in payload
    assert payload["permission_codes"] == [
        "COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ",
        "COMPANY_JOB_READ",
        "COMPANY_TIMEKEEPING_OWN_READ",
        "COMPANY_PAYROLL_STATEMENT_OWN_READ",
    ]
