import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Table

from app.customer_migration.adapter_import import ReviewedCustomerAggregate
from app.customer_migration.models import (
    CustomerMigrationSourceArtifact,
    ServiceLocationSourceIdentity,
)
from app.operational_migration.hcp_migration2_runner import (
    EXPECTED_HYBRID_DIGEST,
    EXPECTED_PARENT_CLOSURE_DIGEST,
    HcpMigration2Runner,
    ProtectedSource4Loader,
    SafeEvidenceError,
    _safe_json,
)


def _check_constraints(table: Table) -> dict[str, str]:
    constraints = table.constraints
    return {
        item.name: str(item.sqltext)
        for item in constraints
        if getattr(item, "sqltext", None) is not None and item.name is not None
    }


def test_source4_staging_and_location_lineage_require_master() -> None:
    artifact = _check_constraints(CustomerMigrationSourceArtifact.__table__)
    location = _check_constraints(ServiceLocationSourceIdentity.__table__)
    assert (
        "master_run_id IS NOT NULL"
        in artifact["ck_customer_source4_artifact_master_required"]
    )
    assert (
        "hybrid_admission_digest IS NOT NULL"
        in artifact["ck_customer_source4_artifact_master_required"]
    )
    assert (
        "master_run_id IS NOT NULL"
        in location["ck_service_location_source4_lineage_required"]
    )
    assert (
        "source_digest IS NOT NULL"
        in location["ck_service_location_source4_lineage_required"]
    )


def test_reviewed_location_native_identities_must_reconcile() -> None:
    with pytest.raises(ValueError, match="source identities do not reconcile"):
        ReviewedCustomerAggregate(
            row_number=2,
            source_identity="cus_1",
            source_identity_sha256=(
                "2908905ede164ca82eb939db65fc99e1ad58c05c05a7046c948e84f687bb1219"
            ),
            source_row_sha256="a" * 64,
            customer_json='{"customer_type":"residential","display_name":"safe"}',
            contact_json=None,
            service_location_json=(),
            billing_address_json=None,
            service_location_source_identities=("adr_1",),
        )


def test_malformed_protected_json_never_exposes_payload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "PRIVATE-CUSTOMER-NAME-AND-ADDRESS"
    path = tmp_path / "page-safe-id.json"
    path.write_text('{"private":"' + secret)
    with pytest.raises(SafeEvidenceError) as captured:
        _safe_json(path)
    rendered = str(captured.value)
    assert captured.value.code == "protected_json_invalid"
    assert secret not in rendered
    assert secret not in capsys.readouterr().out
    assert path.name not in rendered


def test_safe_error_never_stringifies_protected_value() -> None:
    protected = {"name": "PRIVATE NAME", "address": "PRIVATE ADDRESS"}
    error = SafeEvidenceError("safe_code", "f" * 64)
    assert json.dumps(protected) not in str(error)
    assert "PRIVATE" not in str(error)


@pytest.mark.asyncio
async def test_runner_boundary_redacts_unexpected_protected_exception() -> None:
    runner = HcpMigration2Runner()
    runner._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=ValueError("PRIVATE-CUSTOMER-NAME-AND-ADDRESS")
    )
    with pytest.raises(SafeEvidenceError) as captured:
        await runner.execute(None, context=None, target=None, plan=None)  # type: ignore[arg-type]
    assert captured.value.code == "source4_runner_failed"
    assert "PRIVATE" not in str(captured.value)


@pytest.mark.skipif(
    not (
        Path.home()
        / ".acp-enterprise/migration/housecall-pro/hcp-source-4-20260827T223858Z"
    ).exists(),
    reason="protected SOURCE.4 qualification evidence is not installed",
)
def test_protected_source4_qualification_emits_safe_metadata_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = Path.home() / ".acp-enterprise/migration/housecall-pro"
    loader = ProtectedSource4Loader(
        root / "hcp-source-4-20260827T223858Z",
        root
        / "hcp-source-3-controls/derived/AllCountyPlumbingandLeak_customer_export.csv",
    )
    composition = loader.load_customers()
    receipts = loader.verify_owner_receipts(
        root / "hcp-migration-1a-20260828T120000Z/owner/bindings"
    )
    assert composition.admission.digest == EXPECTED_HYBRID_DIGEST
    assert composition.parent_closure.digest == EXPECTED_PARENT_CLOSURE_DIGEST
    assert composition.safe_counts == {
        "api_customers": 5253,
        "referenced_details": 43,
        "control_assertions": 5248,
        "customer_union": 5296,
        "contacts": 4148,
        "locations": 5339,
        "location_exceptions": 294,
        "job_parent_references": 5801,
    }
    assert len(receipts) == 5
    assert capsys.readouterr().out == ""
