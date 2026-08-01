import csv
from io import StringIO

import pytest

from app.customer_migration.housecall_pro_adapter import (
    HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS,
)
from app.customer_migration.location_expansion import (
    CustomerLocationClassification,
    LocationOwnerDisposition,
    classify_location_expansion,
    exact_job_unlock_counts,
    validate_owner_disposition,
)


def _source(*, changed: bool = False) -> bytes:
    headers = sorted(HOUSECALL_PRO_CUSTOMER_EXPORT_CONTRACTS[2].headers)
    row = dict.fromkeys(headers, "")
    row.update(
        {
            "ID": "customer-1",
            "Customer Type": "Business",
            "Display Name": "Redacted",
            "Address_1 Street Line 1": "1 Main St" if not changed else "2 Main St",
            "Address_1 City": "City",
            "Address_1 State": "FL",
            "Address_1 Postal Code": "32000",
            "Address_2 Street Line 1": "3 Main St",
            "Address_2 City": "City",
            "Address_2 State": "FL",
            "Address_2 Postal Code": "32000",
        }
    )
    target = StringIO(newline="")
    writer = csv.DictWriter(target, fieldnames=headers)
    writer.writeheader()
    writer.writerow(row)
    return target.getvalue().encode()


def test_multi_property_evidence_fails_closed_without_native_location_id() -> None:
    result = classify_location_expansion(
        source=_source(changed=True),
        prior_source=_source(),
        imported_customer_ids=(),
    )
    assert result.multi_property_customers == 1
    assert result.classification_totals["commercial_property_manager"] == 1
    assert result.classification_totals["ambiguous_service_location"] == 1
    assert result.classification_totals["unsupported_source_evidence"] == 2
    assert result.execution_gate == "BLOCKED — NATIVE SERVICE LOCATION ID REQUIRED"
    subject = result.subjects[0]
    assert (
        CustomerLocationClassification.COMMERCIAL_PROPERTY_MANAGER
        in subject.classifications
    )
    with pytest.raises(ValueError, match="native stable"):
        validate_owner_disposition(subject, LocationOwnerDisposition.APPROVE_LOCATION)


def test_exact_job_unlocks_remain_potential_until_location_import() -> None:
    assert exact_job_unlock_counts(
        exact_multi_property_address_matches=141, nonmatching_addresses=27
    ) == {
        "potentially_unlocked_after_approved_location_import": 141,
        "owner_review_required": 27,
        "currently_unlocked": 0,
    }


def test_unknown_schema_fails_closed() -> None:
    with pytest.raises(ValueError, match="registered schema"):
        classify_location_expansion(
            source=b"ID,Address\n1,1 Main St\n",
            prior_source=None,
            imported_customer_ids=(),
        )
