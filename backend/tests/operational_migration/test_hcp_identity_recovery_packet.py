import pytest
from app.operational_migration.hcp_identity_recovery_packet import (
    CONFLICT,
    EXACT,
    HELD,
    INCORRECT,
    MISSING,
    build_recovery_package,
)


def _row(source: str, disposition: str, **values: object) -> dict[str, object]:
    return {
        "domain": values.pop("domain", "customer"),
        "source_id": source,
        "cohort": "SAFE_UPDATE",
        "disposition": disposition,
        "reason": "evidence",
        "evidence_digest": source.removeprefix("cus_").zfill(64),
        "native_id": values.pop("native_id", None),
        "legacy_identity_id": values.pop("legacy_identity_id", None),
        **values,
    }


def test_builds_complete_candidate_bound_package_and_propagates_holds() -> None:
    rows = [
        _row("cus_1", "BINDING_ALREADY_PRESENT"),
        _row(
            "cus_2",
            "NATIVE_SUCCESSOR_MISSING",
            native_id="native-2",
            legacy_identity_id="legacy-2",
        ),
        _row("cus_3", "UNSUPPORTED"),
        _row("cus_4", "CONFLICTING_SOURCE4_BINDING"),
        _row("cus_5", "NATIVE_SUCCESSOR_MISSING"),
        _row("job_6", "PROVABLE_NATIVE_SUCCESSOR_BINDING", domain="job"),
    ]
    inventory = {
        "contract": "hcp-update-runtime-successor-inventory/v1",
        "mutation_authority": "none",
        "protected_authority": "a" * 40,
        "schema_head": "head",
        "records": rows,
    }
    dependencies = {
        (row["domain"], row["source_id"]): ()
        for row in rows  # type: ignore[index]
    }
    dependencies[("job", "job_6")] = (("customer", "cus_2"),)

    result = build_recovery_package(inventory, dependencies, expected_bindings=6)

    assert result["binding_count"] == 6
    assert result["independent_recovery_count"] == 1
    assert result["classification_counts"] == {
        CONFLICT: 1,
        EXACT: 1,
        HELD: 2,
        INCORRECT: 1,
        MISSING: 1,
    }
    assert len(result["digest"]) == 64


def test_rejects_incomplete_protected_inventory() -> None:
    inventory = {
        "contract": "hcp-update-runtime-successor-inventory/v1",
        "mutation_authority": "none",
        "records": [],
    }

    with pytest.raises(ValueError, match="exactly 417 rows"):
        build_recovery_package(inventory, {})


def test_rejects_unknown_dependency_parent() -> None:
    row = _row("cus_1", "BINDING_ALREADY_PRESENT")
    inventory = {
        "contract": "hcp-update-runtime-successor-inventory/v1",
        "mutation_authority": "none",
        "records": [row],
    }
    dependencies = {
        ("customer", "cus_1"): (("customer", "cus_missing"),),
    }

    with pytest.raises(ValueError, match="unknown parent"):
        build_recovery_package(inventory, dependencies, expected_bindings=1)
