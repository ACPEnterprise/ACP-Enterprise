import csv
import hashlib
import json
from datetime import datetime, timezone

import pytest

from app.operational_migration.job_source_readiness import (
    CURRENT_JOB_HEADERS,
    JOB_HEADERS,
    JobSourceSchema,
    detect_schema,
    inventory_artifact,
    make_readiness_package,
    reconcile_legacy_exports,
    schema_fingerprint,
    service_location_dispositions,
)


def _csv(headers: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    from io import StringIO

    value = StringIO(newline="")
    writer = csv.DictWriter(value, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return value.getvalue().encode()


def _legacy(identifier: str, *, status: str = "DONE", address: str = "1 Main St"):
    row = dict.fromkeys(JOB_HEADERS, "")
    row.update(
        {
            "HCP Id": identifier,
            "Job Status": status,
            "Address": address,
            "Customer": "Exact Customer",
        }
    )
    return row


def test_schema_registry_fails_closed_and_does_not_promote_job_number() -> None:
    assert detect_schema(JOB_HEADERS) is JobSourceSchema.LEGACY_JOB
    assert detect_schema(CURRENT_JOB_HEADERS) is JobSourceSchema.CURRENT_JOB
    assert detect_schema(("Job #", "Status")) is JobSourceSchema.UNREGISTERED
    current = inventory_artifact(
        filename="current.csv",
        secure_location="$SOURCE/current.csv",
        source=_csv(
            CURRENT_JOB_HEADERS,
            [
                dict(
                    zip(
                        CURRENT_JOB_HEADERS,
                        (
                            "42",
                            "Repair",
                            "Completed",
                            "Customer",
                            "2026-01-01T10:00:00-05:00",
                            "",
                            "$1.00",
                            "1",
                        ),
                        strict=True,
                    )
                )
            ],
        ),
    )
    assert current.schema_version == "housecall_pro_jobs_export_2026_v1"
    assert current.identity_semantics == "job_number_unproven"
    assert current.stable_identifiers == ()
    assert not current.authoritative_for_migration


def test_cross_export_reconciliation_preserves_versions_and_target_boundary() -> None:
    earlier = _csv(JOB_HEADERS, [_legacy("a"), _legacy("b"), _legacy("old")])
    later = _csv(
        JOB_HEADERS,
        [_legacy("a"), _legacy("b", status="IN PROGRESS"), _legacy("new")],
    )
    result = reconcile_legacy_exports(
        earlier=earlier, later=later, imported_source_ids=("a", "target-only")
    )
    assert result.exact_identity_matches == 1
    assert result.same_identity_updated_source_version == 1
    assert result.earlier_source_only == 1
    assert result.later_source_only == 1
    assert result.deleted_or_missing_historical_identity == 1
    assert result.already_imported_identity_matches == 1
    assert result.target_only_identity == 1


def test_service_location_breakdown_is_exact_and_nonfuzzy() -> None:
    source = _csv(
        JOB_HEADERS,
        [
            _legacy("blank", address=""),
            _legacy("missing", address="9 Missing Rd"),
            _legacy("multiple", address="2 Multi Rd"),
        ],
    )
    phase1 = {
        "dispositions": [
            {"row_number": number, "category": "service_location_not_migrated"}
            for number in (2, 3, 4)
        ]
    }
    customer_review = {
        "aggregates": [
            {
                "source_identity": "accepted",
                "customer_json": json.dumps({"display_name": "Exact Customer"}),
                "contact_json": None,
                "service_location_json": [],
            },
            {
                "source_identity": "owner",
                "customer_json": json.dumps({"display_name": "Exact Customer"}),
                "contact_json": None,
                "service_location_json": [
                    json.dumps({"address": "2 Multi Rd"}),
                    json.dumps({"address": "3 Multi Rd"}),
                ],
            },
        ]
    }
    result = service_location_dispositions(
        source=source,
        phase1_review=phase1,
        customer_review=customer_review,
        customer_manifest={"ordered_source_identities": ["accepted"]},
    )
    assert sum(result.values()) == 3
    assert result["blank_source_address"] == 1
    assert result["customer_identity_ambiguous"] == 2
    assert result["incomplete_source_address"] == 0


def test_readiness_package_blocks_incomplete_source() -> None:
    source = _csv(JOB_HEADERS, [_legacy("a")])
    inventory = inventory_artifact(
        filename="legacy.csv", secure_location="$SOURCE/legacy.csv", source=source
    )
    reconciliation = reconcile_legacy_exports(
        earlier=source, later=source, imported_source_ids=("a",)
    )
    package = make_readiness_package(
        generated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        inventory=(inventory,),
        reconciliation=reconciliation,
        location_dispositions={"known": 642},
    )
    assert package.result == "BLOCKED — SOURCE REQUIRED"
    assert package.completeness["unavailable_due_to_incomplete_export"] == 4685
    payload = package.model_dump(mode="json")
    assert "Exact Customer" not in json.dumps(payload)
    assert len(package.package_sha256) == 64
    assert (
        schema_fingerprint(JOB_HEADERS)
        == hashlib.sha256(
            json.dumps(list(JOB_HEADERS), separators=(",", ":")).encode()
        ).hexdigest()
    )


def test_readiness_package_counts_unproven_current_identities_as_unsupported() -> None:
    legacy_source = _csv(JOB_HEADERS, [_legacy("a")])
    current_source = _csv(
        CURRENT_JOB_HEADERS,
        [dict.fromkeys(CURRENT_JOB_HEADERS, "") for _ in range(2)],
    )
    package = make_readiness_package(
        generated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        inventory=(
            inventory_artifact(
                filename="legacy.csv",
                secure_location="$SOURCE/legacy.csv",
                source=legacy_source,
            ),
            inventory_artifact(
                filename="current.csv",
                secure_location="$SOURCE/current.csv",
                source=current_source,
            ),
        ),
        reconciliation=reconcile_legacy_exports(
            earlier=legacy_source,
            later=legacy_source,
            imported_source_ids=("a",),
        ),
        location_dispositions={"known": 642},
    )
    assert package.cross_export_reconciliation["unsupported_identity"] == 2


def test_unregistered_layout_is_not_authoritative() -> None:
    result = inventory_artifact(
        filename="unknown.csv",
        secure_location="$SOURCE/unknown.csv",
        source=b"Job #,Status\n1,Done\n",
    )
    assert result.schema_version == "unregistered"
    assert not result.row_level
    assert not result.authoritative_for_migration


def test_legacy_reconciliation_rejects_missing_identity() -> None:
    source = _csv(JOB_HEADERS, [_legacy("")])
    with pytest.raises(ValueError, match="nonblank source identities"):
        reconcile_legacy_exports(earlier=source, later=source, imported_source_ids=())
