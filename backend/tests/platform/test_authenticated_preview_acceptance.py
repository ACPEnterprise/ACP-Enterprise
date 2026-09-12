from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.authenticated_preview_acceptance import (
    SCHEDULE_ROUTE,
    AcceptanceBlocked,
    mutation_registry_has_schedule_route,
    read_attestation,
    read_token,
    validate_identity_and_scope,
    validate_origin,
    validate_short_lived_token,
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
            "COMPANY_SCHEDULING_READ",
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
                "expires_at": (now + timedelta(hours=2)).isoformat(),
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
