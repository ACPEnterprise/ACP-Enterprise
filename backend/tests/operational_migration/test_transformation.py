from collections.abc import Mapping

import pytest

from app.operational_migration.service import JobMigrationRecord
from app.operational_migration.transformation import (
    OperationalEntity,
    OperationalTransformationPipeline,
    ParsedSourceExport,
    SourceField,
    TransformationContract,
    TransformationValidationError,
    housecall_pro_operational_pipeline,
)


def build_job(row: Mapping[str, object]) -> JobMigrationRecord:
    status = row["state"]
    if status not in {"new", "completed"}:
        raise TransformationValidationError("unsupported_job_status", fields=("state",))
    return JobMigrationRecord(
        source_id=str(row["record_key"]),
        source_customer_id=str(row["customer_key"]),
        source_service_location_id=str(row["location_key"]),
        status=str(status),
    )


def contract() -> TransformationContract:
    return TransformationContract(
        provider="synthetic_provider",
        entity="job",
        version="declared-v1",
        fields=(
            SourceField("record_key", required=True),
            SourceField("customer_key", required=True),
            SourceField("location_key", required=True),
            SourceField("state", required=True),
            SourceField("optional_summary", required=False),
        ),
        builder=build_job,
    )


def export(
    *,
    columns: tuple[str, ...] = (
        "record_key",
        "customer_key",
        "location_key",
        "state",
    ),
    rows: tuple[Mapping[str, object], ...] = (
        {
            "record_key": "synthetic-job-1",
            "customer_key": "synthetic-customer-1",
            "location_key": "synthetic-location-1",
            "state": "new",
        },
    ),
    version: str = "declared-v1",
) -> ParsedSourceExport:
    return ParsedSourceExport.from_source_bytes(
        entity="job",
        version=version,
        columns=columns,
        rows=rows,
        source_bytes=b"synthetic export bytes",
    )


def pipeline() -> OperationalTransformationPipeline:
    return OperationalTransformationPipeline(
        provider="synthetic_provider", contracts=(contract(),)
    )


@pytest.mark.parametrize(
    "entity",
    [
        "job",
        "appointment",
        "estimate",
        "invoice",
        "payment",
        "note",
        "attachment",
    ],
)
def test_housecall_pro_operational_exports_fail_closed_without_real_contracts(
    entity: OperationalEntity,
) -> None:
    source = ParsedSourceExport.from_source_bytes(
        entity=entity,
        version="unverified-layout",
        columns=("unverified_column",),
        rows=({"unverified_column": "not inspected"},),
        source_bytes=b"synthetic unverified layout",
    )

    report = housecall_pro_operational_pipeline().transform(
        source, expected_source_sha256=source.source_sha256
    )

    assert report.accepted == 0
    assert report.rejected == 1
    assert report.rejections[0].code == "unsupported_export_version"


def test_unknown_columns_reject_the_export_without_guessing() -> None:
    source = export(
        columns=(
            "record_key",
            "customer_key",
            "location_key",
            "state",
            "provider_specific_unknown",
        )
    )

    report = pipeline().transform(source, expected_source_sha256=source.source_sha256)

    assert report.accepted == 0
    assert report.rejected == 1
    assert report.rejections[0].code == "unknown_columns"
    assert report.rejections[0].fields == ("provider_specific_unknown",)


def test_missing_required_columns_and_fields_are_explicit() -> None:
    missing_column = export(
        columns=("record_key", "customer_key", "state"),
        rows=(
            {
                "record_key": "synthetic-job-1",
                "customer_key": "synthetic-customer-1",
                "state": "new",
            },
        ),
    )
    missing_field = export(
        rows=(
            {
                "record_key": "synthetic-job-1",
                "customer_key": "synthetic-customer-1",
                "location_key": " ",
                "state": "new",
            },
        )
    )

    column_report = pipeline().transform(
        missing_column, expected_source_sha256=missing_column.source_sha256
    )
    field_report = pipeline().transform(
        missing_field, expected_source_sha256=missing_field.source_sha256
    )

    assert column_report.rejections[0].code == "missing_required_columns"
    assert column_report.rejections[0].fields == ("location_key",)
    assert field_report.rejections[0].code == "missing_required_fields"
    assert field_report.rejections[0].fields == ("location_key",)


def test_unsupported_versions_and_checksum_mismatches_are_structured() -> None:
    unsupported = export(version="declared-v2")
    bad_checksum = export()

    version_report = pipeline().transform(
        unsupported, expected_source_sha256=unsupported.source_sha256
    )
    checksum_report = pipeline().transform(
        bad_checksum, expected_source_sha256="0" * 64
    )

    assert version_report.rejections[0].code == "unsupported_export_version"
    assert checksum_report.rejections[0].code == "source_checksum_mismatch"


def test_rejections_are_deterministic_and_do_not_include_source_values() -> None:
    source = export(
        rows=(
            {
                "record_key": "sensitive-source-identifier",
                "customer_key": "synthetic-customer-1",
                "location_key": "synthetic-location-1",
                "state": "provider-state-not-mapped",
            },
        )
    )

    first = pipeline().transform(source, expected_source_sha256=source.source_sha256)
    second = pipeline().transform(source, expected_source_sha256=source.source_sha256)

    assert first == second
    assert first.rejections[0].code == "unsupported_job_status"
    assert first.rejections[0].fields == ("state",)
    assert "sensitive-source-identifier" not in repr(first.rejections)


def test_duplicate_source_identities_are_hashed_and_idempotent() -> None:
    row = {
        "record_key": "synthetic-job-duplicate",
        "customer_key": "synthetic-customer-1",
        "location_key": "synthetic-location-1",
        "state": "new",
    }
    source = export(rows=(row, dict(row)))

    first = pipeline().transform(source, expected_source_sha256=source.source_sha256)
    second = pipeline().transform(source, expected_source_sha256=source.source_sha256)

    assert first == second
    assert first.source == 2
    assert first.accepted == 1
    assert first.duplicate == 1
    assert first.rejections[0].code == "duplicate_source_identity"
    assert first.rejections[0].source_id_sha256 is not None
    assert first.rejections[0].source_id_sha256 != row["record_key"]
