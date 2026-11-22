import argparse
import csv
import hashlib
import io
import json
import stat
from pathlib import Path

import pytest
from app.customer_migration.acceptance_cohort import (
    CustomerAcceptanceCohort,
    generate_customer_acceptance_cohort,
)
from app.customer_migration.housecall_pro_adapter import (
    HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS,
)
from pydantic import ValidationError
from scripts.generate_customer_acceptance_cohort import generate

RELEASE_SHA = "a" * 40


def customer_csv() -> bytes:
    contract = HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS[2]
    headers = sorted(contract.headers, reverse=True)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for source_id, display_name in (
        ("provider-001", "Private Alpha Name"),
        ("provider-002", "Private Bravo Name"),
        ("provider-003", "Private Charlie Name"),
        ("provider-004", "Private Delta Name"),
    ):
        writer.writerow(
            {
                header: {
                    "ID": source_id,
                    "Customer Type": "homeowner",
                    "Display Name": display_name,
                    "Email": f"{source_id}@example.invalid",
                    "Do Not Service": "false",
                }.get(header, "")
                for header in headers
            }
        )
    return output.getvalue().encode()


def artifact(*, anchors: tuple[str, ...] = ("provider-004",)):
    source = customer_csv()
    return generate_customer_acceptance_cohort(
        source,
        expected_source_sha256=hashlib.sha256(source).hexdigest(),
        migration_release_sha=RELEASE_SHA,
        mandatory_source_ids=anchors,
        limit=2,
    )


def test_cohort_is_deterministic_bound_and_contains_no_customer_pii() -> None:
    first = artifact()
    second = artifact()

    assert first == second
    assert len(first.selected) == 2
    assert [item.source_identity_sha256 for item in first.selected] == sorted(
        hashlib.sha256(value.encode()).hexdigest()
        for value in ("provider-001", "provider-002", "provider-003")
    )[:2]
    assert [item.source_identity for item in first.mandatory_anchors] == [
        "provider-004"
    ]
    assert first.source_sha256 == hashlib.sha256(customer_csv()).hexdigest()
    assert first.source_system == "housecall_pro"
    assert first.migration_release_sha == RELEASE_SHA
    assert first.transformation_sha256 != first.reviewed_output_sha256
    payload = first.model_dump_json()
    assert "Private" not in payload
    assert "example.invalid" not in payload


def test_contract_rejects_tampered_canonical_artifact() -> None:
    payload = artifact().model_dump(mode="json")
    payload["migration_release_sha"] = "b" * 40

    with pytest.raises(ValidationError, match="artifact digest mismatch"):
        CustomerAcceptanceCohort.model_validate(payload)


@pytest.mark.parametrize(
    ("anchors", "message"),
    [
        (("provider-004", "provider-004"), "must be unique"),
        (("missing-provider",), "absent from reviewed output"),
    ],
)
def test_generator_rejects_duplicate_or_missing_mandatory_anchors(
    anchors: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        artifact(anchors=anchors)


def test_cli_writes_new_canonical_artifact_with_mode_0600(tmp_path: Path) -> None:
    source = customer_csv()
    source_path = tmp_path / "customers.csv"
    output_path = tmp_path / "cohort.json"
    source_path.write_bytes(source)
    arguments = argparse.Namespace(
        source=source_path,
        expected_source_sha256=hashlib.sha256(source).hexdigest(),
        migration_release_sha=RELEASE_SHA,
        mandatory_source_id=["provider-004"],
        limit=2,
        source_system="synthetic-provider",
        output=output_path,
    )

    assert generate(arguments) == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    validated = CustomerAcceptanceCohort.model_validate(payload)
    assert validated.source_system == "synthetic-provider"
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        generate(arguments)


def test_generator_rejects_source_digest_mismatch() -> None:
    with pytest.raises(ValueError, match="source checksum mismatch"):
        generate_customer_acceptance_cohort(
            customer_csv(),
            expected_source_sha256="0" * 64,
            migration_release_sha=RELEASE_SHA,
            mandatory_source_ids=("provider-004",),
            limit=2,
        )


def test_generator_bounds_the_output_cohort() -> None:
    source = customer_csv()
    with pytest.raises(ValueError, match="outside the supported bound"):
        generate_customer_acceptance_cohort(
            source,
            expected_source_sha256=hashlib.sha256(source).hexdigest(),
            migration_release_sha=RELEASE_SHA,
            mandatory_source_ids=("provider-004",),
            limit=1_001,
        )
