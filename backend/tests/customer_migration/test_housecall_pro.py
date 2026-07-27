import pytest

from app.customer_migration.housecall_pro import (
    UnresolvedRowError,
    normalized_header,
    parse_customer,
)


def test_housecall_pro_mapping_builds_existing_customer_domain_schemas() -> None:
    parsed = parse_customer(
        {
            "customer_id": "source-1",
            "display_name": "Example Customer",
            "first_name": "Example",
            "last_name": "Customer",
            "emails": "CUSTOMER@EXAMPLE.TEST",
            "mobile_number": "(727) 555-0101",
            "type": "homeowner",
            "service_address": "101 Test Ave",
            "service_city": "Testville",
            "service_state": "FL",
            "service_postal_code": "33755",
            "billing_address": "PO Box 101",
            "billing_city": "Testville",
            "billing_state": "FL",
            "billing_postal_code": "33756",
        }
    )

    assert parsed.source_id == "source-1"
    assert parsed.customer.customer_type.value == "residential"
    assert parsed.contact is not None
    assert parsed.contact.email == "customer@example.test"
    assert parsed.service_location is not None
    assert parsed.billing_address is not None


def test_housecall_pro_mapping_does_not_fabricate_identity_or_address_parts() -> None:
    with pytest.raises(UnresolvedRowError, match="customer_id"):
        parse_customer({"display_name": "No source identity"})

    with pytest.raises(UnresolvedRowError, match="separate address"):
        parse_customer(
            {
                "customer_id": "source-2",
                "display_name": "Combined Address",
                "service_address": "101 Test Ave",
            }
        )


def test_headers_normalize_without_guessing_semantics() -> None:
    assert normalized_header(" Billing Address Notes ") == "billing_address_notes"
