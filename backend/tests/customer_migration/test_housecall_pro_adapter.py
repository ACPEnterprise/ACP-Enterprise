import csv
import hashlib
import io

import pytest

from app.customer_migration.housecall_pro_adapter import (
    HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS,
    HousecallProCustomerExportAdapter,
    detect_customer_export_contract,
)
from app.customers.schemas import CustomerStatus, CustomerType


def adapter() -> HousecallProCustomerExportAdapter:
    return HousecallProCustomerExportAdapter()


def source_bytes(
    *,
    contract_index: int = 1,
    rows: list[dict[str, str]],
    extra_headers: tuple[str, ...] = (),
) -> bytes:
    contract = HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS[contract_index]
    headers = sorted(contract.headers, reverse=True) + list(extra_headers)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for values in rows:
        writer.writerow({header: values.get(header, "") for header in headers})
    return output.getvalue().encode()


def base_row(*, source_id: str = "synthetic-customer-1") -> dict[str, str]:
    return {
        "ID": source_id,
        "Customer Type": "homeowner",
        "Display Name": "Synthetic Customer",
    }


@pytest.mark.parametrize("contract_index", [0, 1, 2])
def test_detects_actual_versioned_layout_without_column_positions(
    contract_index: int,
) -> None:
    contract = HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS[contract_index]
    headers = sorted(contract.headers, reverse=True)

    detected = detect_customer_export_contract(headers)

    assert detected == contract


def test_450_contract_is_limited_to_verified_header_differences() -> None:
    extended = HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS[1]
    phone_2b = HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS[2]

    assert phone_2b.version == "housecall_pro_customer_450_v1"
    assert phone_2b.headers == (
        extended.headers - {"Email marketing consent", "SMS marketing consent"}
        | {"Do Not Service"}
    )
    assert phone_2b.address_group_count == extended.address_group_count


def test_450_contract_preserves_do_not_service_as_unmapped_evidence() -> None:
    row = base_row()
    row["Do Not Service"] = "synthetic-source-value"
    raw = source_bytes(contract_index=2, rows=[row])

    report = adapter().transform(
        raw, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )

    assert report.schema_version == "housecall_pro_customer_450_v1"
    assert report.accepted == 1
    assert report.records[0].customer.status == CustomerStatus.ACTIVE
    assert report.records[0].unmapped_fields == {
        "Do Not Service": "synthetic-source-value"
    }


def test_unknown_columns_fail_closed() -> None:
    raw = source_bytes(rows=[base_row()], extra_headers=("Unapproved Column",))

    report = adapter().transform(
        raw, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )

    assert report.schema_version is None
    assert report.accepted == 0
    assert report.rejections[0].code == "unsupported_customer_export_schema"


def test_repeated_address_groups_are_detected_and_mapped_generically() -> None:
    row = base_row()
    row.update(
        {
            "Address_2 Street Line 1": "2 Synthetic Way",
            "Address_2 City": "Example",
            "Address_2 State": "EX",
            "Address_2 Postal Code": "00002",
            "Address_2 Notes": "Synthetic service-location note",
            "Address_61 Street Line 1": "61 Synthetic Way",
            "Address_61 City": "Example",
            "Address_61 State": "EX",
            "Address_61 Postal Code": "00061",
            "Address_61 Billing?": "true",
        }
    )
    raw = source_bytes(rows=[row])

    report = adapter().transform(
        raw, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )

    assert report.accepted == 1
    assert len(report.records[0].service_locations) == 1
    assert report.records[0].service_locations[0].address == "2 Synthetic Way"
    assert report.records[0].billing_address is not None
    assert report.records[0].billing_address.address == "61 Synthetic Way"


def test_incomplete_secondary_address_is_a_child_exception() -> None:
    row = base_row()
    row.update(
        {
            "Address_2 Street Line 1": "2 Synthetic Way",
            "Address_2 City": "Example",
            "Address_2 State": "EX",
            "Address_2 Postal Code": "00002",
            "Address_37 Street Line 1": "37 Synthetic Way",
            "Address_37 State": "EX",
            "Address_37 Postal Code": "00037",
        }
    )
    raw = source_bytes(rows=[row])

    first = adapter().transform(
        raw, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )
    second = adapter().transform(
        raw, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )

    assert first == second
    assert first.accepted == 1
    assert first.rejected == 0
    assert len(first.records[0].service_locations) == 1
    assert first.records[0].service_locations[0].address == "2 Synthetic Way"
    assert first.records[0].billing_address is None
    assert len(first.records[0].incomplete_address_groups) == 1
    assert first.records[0].incomplete_address_groups[0].address_group_number == 37
    assert len(first.child_exceptions) == 1
    exception = first.child_exceptions[0]
    assert exception.address_group_number == 37
    assert exception.missing_fields == ("Address_37 City",)
    assert exception.reason_code == "incomplete_address_group"
    assert exception.contract_version == "housecall_pro_customer_451_v1"
    assert exception.source_id_sha256 != "synthetic-customer-1"
    assert "37 Synthetic Way" not in repr(exception)


def test_incomplete_billing_address_is_a_child_exception() -> None:
    row = base_row()
    row.update(
        {
            "Address_4 Street Line 1": "4 Synthetic Way",
            "Address_4 City": "Example",
            "Address_4 State": "EX",
            "Address_4 Postal Code": "00004",
            "Address_5 Street Line 1": "5 Synthetic Way",
            "Address_5 State": "EX",
            "Address_5 Postal Code": "00005",
            "Address_5 Billing?": "true",
        }
    )
    raw = source_bytes(rows=[row])

    report = adapter().transform(
        raw, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )

    assert report.accepted == 1
    assert len(report.records[0].service_locations) == 1
    assert report.records[0].billing_address is None
    assert len(report.records[0].incomplete_address_groups) == 1
    assert report.child_exceptions[0].address_group_number == 5
    assert report.child_exceptions[0].missing_fields == ("Address_5 City",)
    assert report.child_exceptions[0].reason_code == "incomplete_address_group"


def test_maps_only_supported_fields_and_preserves_unmapped_values() -> None:
    row = base_row()
    row.update(
        {
            "First Name": "Synthetic",
            "Last Name": "Person",
            "Company": "Synthetic Company",
            "Customer Type": "business",
            "Role": "Synthetic Role",
            "Additional Emails": "synthetic-unmapped@example.invalid",
            "Tags": "Do Not Service",
            "Customer created at": "synthetic-unmapped-timestamp",
        }
    )
    raw = source_bytes(rows=[row])

    report = adapter().transform(
        raw, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )
    record = report.records[0]

    assert record.customer.customer_type == CustomerType.COMMERCIAL
    assert record.customer.legal_name == "Synthetic Company"
    assert record.contact is not None
    assert record.contact.title == "Synthetic Role"
    assert record.unmapped_fields == {
        "Additional Emails": "synthetic-unmapped@example.invalid",
        "Customer created at": "synthetic-unmapped-timestamp",
        "Tags": "Do Not Service",
    }
    assert record.customer.status == CustomerStatus.ACTIVE


def test_empty_or_unknown_customer_type_fails_closed() -> None:
    empty = base_row()
    empty["Customer Type"] = ""
    unknown = base_row(source_id="synthetic-customer-2")
    unknown["Customer Type"] = "unmapped-type"
    raw = source_bytes(rows=[empty, unknown])

    report = adapter().transform(
        raw, expected_source_sha256=hashlib.sha256(raw).hexdigest()
    )

    assert report.accepted == 0
    assert [item.code for item in report.rejections] == [
        "missing_required_field",
        "unsupported_customer_type",
    ]


def test_duplicate_and_idempotent_transformation_behavior() -> None:
    raw = source_bytes(rows=[base_row(), base_row()])
    expected = hashlib.sha256(raw).hexdigest()

    first = adapter().transform(raw, expected_source_sha256=expected)
    second = adapter().transform(raw, expected_source_sha256=expected)

    assert first == second
    assert first.source == 2
    assert first.accepted == 1
    assert first.duplicate == 1
    assert first.rejections[0].code == "duplicate_source_identity"
    assert first.rejections[0].source_id_sha256 != "synthetic-customer-1"


def test_source_checksum_must_match() -> None:
    raw = source_bytes(rows=[base_row()])

    report = adapter().transform(raw, expected_source_sha256="0" * 64)

    assert report.accepted == 0
    assert report.rejections[0].code == "source_checksum_mismatch"
