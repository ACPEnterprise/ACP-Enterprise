from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.acceptance_identity_provisioning_contract import (
    ProvisioningBlocked,
    attest,
    attestation_output_path,
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

MATRIX_PATH = Path(__file__).parents[2] / "operations/preview-authenticated-acceptance-matrix.v1.json"
REPORT_PATH = Path(__file__).parents[2] / "operations/preview-authenticated-acceptance-report.v1.json"
AUTHORITY_PATH = Path(__file__).parents[2] / "operations/preview-persona-contract-authority.v1.json"
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
                "fixture_version": "preview.synthetic.tenant.v1",
                "environment": "preview",
                "synthetic_marker": "SYNTHETIC_BETA_ONLY",
                "real_data_access": False,
                "company_id": "31ba6867-2d8a-55dd-9e34-d67c684ee41c",
                "branch_id": "95bf7a14-09b0-51b6-b3cb-7946523ec093",
                "user_id": "00000000-0000-0000-0000-000000000021",
                "session_id": "00000000-0000-0000-0000-000000000022",
                "persona": "csr",
                "deployed_sha": "7cdfb183c1d07e064eba88cc547df4f090708ff6",
                "protected_authority_sha": "7cdfb183c1d07e064eba88cc547df4f090708ff6",
                "frontend_sha256": "0fe86ebb45767edfbffeaf6c80645bf60da1860ebf141369167895da7eea97e8",
                "schema_head": "g7i9k1m3o5q7",
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
                "permission_digest": hashlib.sha256(
                    json.dumps(
                        sorted(
                            {
                                "COMPANY_CUSTOMER_READ",
                                "COMPANY_JOB_READ",
                                "COMPANY_JOB_MANAGE",
                                "COMPANY_SCHEDULING_READ",
                                "COMPANY_SCHEDULING_MANAGE",
                                "COMPANY_DISPATCH_READ",
                            }
                        ),
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                "mutation_allowlist": [],
                "mutation_maximum": [SCHEDULE_ROUTE],
                "fixture_references": {
                    "customer_id": "00000000-0000-0000-0000-000000000011",
                    "job_id": "00000000-0000-0000-0000-000000000012",
                    "appointment_id": "00000000-0000-0000-0000-000000000013",
                },
                "issued_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=2)).isoformat(),
                "session_expires_at": (now + timedelta(minutes=30)).isoformat(),
                "authorized_by": "enterprise-release",
                "audit_event_id": "00000000-0000-0000-0000-000000000023",
                "audit_actor_identity": "preview.synthetic.fixture.orchestrator.v1",
            }
        ),
        encoding="utf-8",
    )
    attestation.chmod(0o600)
    with pytest.raises(AcceptanceBlocked, match="audit actor"):
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
    contract = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    assert contract["origin"] == PREVIEW_ORIGIN
    assert contract["environment"] == "preview"
    assert contract["production_access"] is False
    assert contract["lifetimes"]["access_token_maximum_seconds"] == 3600
    assert frozenset(contract["prohibited_permissions"]) == PROHIBITED_PERMISSIONS
    for persona in contract["personas"].values():
        name = persona["consumer_id"]
        permissions = frozenset(persona["permissions"])
        assert permissions == REQUIRED_PERMISSIONS[name]
        assert not permissions & PROHIBITED_PERMISSIONS


def test_authority_packet_matches_runner_and_permission_digests() -> None:
    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    assert authority["tenant"] == {
        "fixture_version": "preview.synthetic.tenant.v1",
        "fixture_key": "acp-employee-beta-v1",
        "company_id": "31ba6867-2d8a-55dd-9e34-d67c684ee41c",
        "branch_id": "95bf7a14-09b0-51b6-b3cb-7946523ec093",
        "has_all_branch_access": False,
    }
    for consumer_id, permissions in REQUIRED_PERMISSIONS.items():
        persona = next(
            value
            for value in authority["personas"].values()
            if value["consumer_id"] == consumer_id
        )
        assert frozenset(persona["permissions"]) == permissions
        encoded = json.dumps(sorted(permissions), separators=(",", ":")).encode()
        assert persona["permission_digest"] == hashlib.sha256(encoded).hexdigest()
        assert persona["mutation_allowlist_default"] == []
        assert set(persona["mutation_allowlist_maximum"]) <= {SCHEDULE_ROUTE}
    assert authority["personas"]["QBO_READ"]["permissions"] == [
        "COMPANY_ACCOUNTING_REPORT_READ"
    ]
    assert authority["audit_actor"]["primitive_state"] == "MISSING"
    assert authority["audit_actor"]["tenant_membership"] is False
    assert authority["audit_actor"]["production_allowed"] is False
    assert authority["audit_actor"]["acp_main_allowed"] is False


def test_schema_security_constants_match_canonical_authority() -> None:
    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    schema = json.loads(
        (Path(__file__).parents[2] / "operations/preview-acceptance-attestation.v1.schema.json")
        .read_text(encoding="utf-8")
    )
    properties = schema["properties"]
    assert properties["company_id"]["const"] == authority["tenant"]["company_id"]
    assert properties["branch_id"]["const"] == authority["tenant"]["branch_id"]
    assert properties["protected_authority_sha"]["const"] == authority[
        "protected_authority"
    ]
    assert properties["deployed_sha"]["const"] == authority["release_contract"][
        "deployed_sha_required"
    ]
    assert properties["schema_head"]["const"] == authority["release_contract"][
        "schema_head_required"
    ]
    assert properties["frontend_sha256"]["const"] == authority["release_contract"][
        "frontend_sha256_required"
    ]
    for conditional in schema["allOf"]:
        persona_name = conditional["if"]["properties"]["persona"]["const"]
        persona = next(
            value
            for value in authority["personas"].values()
            if value["consumer_id"] == persona_name
        )
        constrained = conditional["then"]["properties"]
        assert constrained["permission_codes"]["const"] == persona["permissions"]
        assert constrained["permission_digest"]["const"] == persona["permission_digest"]


def test_python_consumers_do_not_duplicate_permission_codes() -> None:
    scripts = Path(__file__).parents[2] / "scripts"
    for name in (
        "authenticated_preview_acceptance.py",
        "acceptance_identity_provisioning_contract.py",
    ):
        assert "COMPANY_" not in (scripts / name).read_text(encoding="utf-8")


def test_attestation_output_path_is_canonical() -> None:
    assert attestation_output_path(
        Path("/run/secrets/acp-preview-acceptance/v1/run-1/csr/attestation.json"),
        "csr",
    ) == Path("/run/secrets/acp-preview-acceptance/v1/run-1/csr/attestation.json")
    with pytest.raises(ProvisioningBlocked):
        attestation_output_path(Path("/tmp/attestation.json"), "csr")


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
            "company_id": "31ba6867-2d8a-55dd-9e34-d67c684ee41c",
            "branch_id": "95bf7a14-09b0-51b6-b3cb-7946523ec093",
        },
    )()
    result = plan(arguments)
    assert result["mutation_performed"] is False
    assert result["classification"] == "BLOCKED_MISSING_PLATFORM_SERVICE_PRINCIPAL"
    arguments.synthetic_login = "person@example.com"
    with pytest.raises(ProvisioningBlocked):
        plan(arguments)


def test_enterprise_attestation_is_restricted_and_contains_no_token() -> None:
    output = Path(
        "/run/secrets/acp-preview-acceptance/v1/test-run/employee/attestation.json"
    )
    arguments = type(
        "Arguments",
        (),
        {
            "persona": "employee",
            "company_id": "31ba6867-2d8a-55dd-9e34-d67c684ee41c",
            "branch_id": "95bf7a14-09b0-51b6-b3cb-7946523ec093",
            "user_id": "00000000-0000-0000-0000-000000000003",
            "session_id": "00000000-0000-0000-0000-000000000004",
            "audit_event_id": "00000000-0000-0000-0000-000000000005",
            "authorized_by": "enterprise-release",
            "audit_actor_identity": "preview.synthetic.fixture.orchestrator.v1",
            "deployed_sha": "a" * 40,
            "protected_authority_sha": "b" * 40,
            "frontend_sha256": "c" * 64,
            "schema_head": "d4f6h8j0l2n4",
            "session_expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
            "allow_mutation": [],
            "fixture_reference": [
                "job_id=00000000-0000-0000-0000-000000000006"
            ],
            "ttl_seconds": 3600,
            "output": output,
        },
    )()
    with pytest.raises(ProvisioningBlocked, match="service principal"):
        attest(arguments)
    assert not output.exists()


def test_attestation_rejects_mutation_outside_persona_contract() -> None:
    arguments = type(
        "Arguments",
        (),
        {
            "persona": "employee",
            "company_id": "31ba6867-2d8a-55dd-9e34-d67c684ee41c",
            "branch_id": "95bf7a14-09b0-51b6-b3cb-7946523ec093",
            "user_id": "00000000-0000-0000-0000-000000000003",
            "session_id": "00000000-0000-0000-0000-000000000004",
            "audit_event_id": "00000000-0000-0000-0000-000000000005",
            "authorized_by": "enterprise-release",
            "audit_actor_identity": "preview.synthetic.fixture.orchestrator.v1",
            "deployed_sha": "a" * 40,
            "protected_authority_sha": "b" * 40,
            "frontend_sha256": "c" * 64,
            "schema_head": "d4f6h8j0l2n4",
            "session_expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
            "allow_mutation": ["/api/v1/timekeeping/me/job-clock/start"],
            "fixture_reference": [
                "job_id=00000000-0000-0000-0000-000000000006"
            ],
            "ttl_seconds": 3600,
            "output": Path(
                "/run/secrets/acp-preview-acceptance/v1/test-run/employee/attestation.json"
            ),
        },
    )()
    with pytest.raises(ProvisioningBlocked):
        attest(arguments)
