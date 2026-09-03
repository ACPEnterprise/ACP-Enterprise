import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_successor_reconciliation_command import (
    SuccessorReadAuthority,
    sealed_identities,
)


def test_authority_is_required_and_must_be_private(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(SafeEvidenceError) as caught:
        SuccessorReadAuthority.load(missing)
    assert caught.value.code == "successor_authority_invalid"

    authority = tmp_path / "authority.json"
    authority.write_text(json.dumps({"contract": "wrong"}))
    authority.chmod(0o644)
    with pytest.raises(SafeEvidenceError) as caught:
        SuccessorReadAuthority.load(authority)
    assert caught.value.code == "successor_authority_permissions_unsafe"


def test_sealed_plan_extraction_covers_operational_domains() -> None:
    customer = SimpleNamespace(
        source_identity="customer-1",
        service_location_source_identities=("location-1", "location-2"),
    )
    plan = SimpleNamespace(
        customers=SimpleNamespace(reviewed=SimpleNamespace(aggregates=(customer,))),
        jobs=(SimpleNamespace(source_id="job-1"),),
        appointments=(SimpleNamespace(source_id="appointment-1"),),
        estimates=(SimpleNamespace(source_id="estimate-1"),),
        invoices=(SimpleNamespace(source_id="invoice-1"),),
        payments=(SimpleNamespace(source_id="payment-1"),),
    )
    identities = sealed_identities(plan)
    assert {(item.domain, item.source_id) for item in identities} == {
        ("customer", "customer-1"),
        ("service_location", "location-1"),
        ("service_location", "location-2"),
        ("job", "job-1"),
        ("appointment", "appointment-1"),
        ("estimate", "estimate-1"),
        ("invoice", "invoice-1"),
        ("payment", "payment-1"),
    }
